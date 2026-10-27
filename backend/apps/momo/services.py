"""
Mobile money services — create intents, process webhooks, confirm payments.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    MomoProviderConfig, PaymentIntent, DisbursementIntent,
)
from .providers.base import get_provider, MomoProviderError

logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================
def _generate_reference(org, prefix):
    today = timezone.now().strftime('%Y%m%d')
    base = f'{prefix}-{org.code.upper()}-{today}'
    from .models import PaymentIntent as PI, DisbursementIntent as DI
    Model = PI if prefix == 'MOMO' else DI
    last = Model.objects.filter(
        organization=org, reference__startswith=base,
    ).aggregate(m=Max('reference'))['m']
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f'{base}-{seq:05d}'


def _get_config(org, provider_code, branch=None, transaction_type='COLLECTION'):
    """
    Return the active MomoProviderConfig for this org / provider / type.
    Preference order:
      1. Branch-specific config (if a branch is provided)
      2. Org-wide default (branch IS NULL)
    """
    if branch is not None:
        cfg = MomoProviderConfig.objects.filter(
            organization=org,
            branch=branch,
            provider_code=provider_code,
            is_active=True,
            transaction_type=transaction_type, # <--- ADDED
        ).first()
        if cfg:
            return cfg

    cfg = MomoProviderConfig.objects.filter(
        organization=org,
        branch__isnull=True,
        provider_code=provider_code,
        is_active=True,
        transaction_type=transaction_type, # <--- ADDED
    ).first()
    if cfg:
        return cfg

    branch_label = f' for branch {branch.code}' if branch else ''
    raise ValueError(
        f'No active {provider_code} ({transaction_type}) config for {org.name}{branch_label}. '
        f'Configure it under Admin → Mobile Money.'
    )


# ============================================================
# Inbound (Collections)
# ============================================================
class CollectionService:

    @staticmethod
    @transaction.atomic
    def initiate(org, client, amount, phone, provider_code,
                 loan=None, description='', user=None, branch=None):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive.')

        # Resolve branch: explicit arg > client's branch > loan's branch
        if branch is None:
            if client and getattr(client, 'branch_id', None):
                branch = client.branch
            elif loan and getattr(loan, 'branch_id', None):
                branch = loan.branch

        # Pass transaction_type='COLLECTION'
        config = _get_config(org, provider_code, branch=branch, transaction_type='COLLECTION')
        provider = get_provider(config)

        reference = _generate_reference(org, 'MOMO')

        intent = PaymentIntent.objects.create(
            organization=org,
            branch=branch,
            client=client,
            loan=loan,
            provider_code=provider_code,
            reference=reference,
            amount=amount,
            phone=phone,
            status='PENDING',
            expires_at=timezone.now() + timedelta(hours=24),
            raw_request={
                'amount': str(amount),
                'phone': phone,
                'description': description,
                'provider': provider_code,
                'branch': branch.code if branch else None,
            },
        )

        try:
            result = provider.collect(
                reference=reference,
                amount=amount,
                phone=phone,
                description=description,
            )
        except MomoProviderError as e:
            intent.status = 'FAILED'
            intent.error = str(e)
            intent.raw_response = e.raw
            intent.save()
            raise

        intent.provider_txn_id = result.get('provider_txn_id', '')
        intent.raw_response = result.get('raw', {})
        provider_status = result.get('status', 'PENDING')

        if provider_status == 'CONFIRMED':
            intent.status = 'CONFIRMED'
            intent.confirmed_at = timezone.now()
            intent.save()
            CollectionService._record_payment(intent, user)
        else:
            intent.status = 'PENDING'
            intent.save()

        return intent

    @staticmethod
    @transaction.atomic
    def process_webhook(provider_code, payload, headers, body_bytes, org=None):
        """
        Handle a provider callback: find the intent, mark it confirmed,
        and post the payment to the GL.
        """
        if org:
            configs = MomoProviderConfig.objects.filter(
                organization=org, provider_code=provider_code, 
                is_active=True, 
                transaction_type='COLLECTION' # <--- ADDED
            )
        else:
            configs = MomoProviderConfig.objects.filter(
                provider_code=provider_code, 
                is_active=True,
                transaction_type='COLLECTION' # <--- ADDED
            )

        parsed = None
        intent = None

        for cfg in configs:
            provider = get_provider(cfg)
            try:
                if not provider.verify_webhook(headers, body_bytes):
                    continue
                parsed = provider.parse_webhook(payload)
                if parsed.get('provider_txn_id'):
                    intent = PaymentIntent.objects.filter(
                        provider_code=provider_code,
                        provider_txn_id=parsed['provider_txn_id'],
                        organization=cfg.organization,
                    ).first()
                if intent:
                    break
            except Exception as e:
                logger.warning(f'Webhook verify failed for {provider_code}: {e}')
                continue

        if not intent:
            logger.warning(
                f'No matching intent for webhook: {parsed}'
            )
            return None

        if intent.status in ('CONFIRMED', 'FAILED', 'CANCELLED'):
            # Idempotent — already handled
            return intent

        intent.raw_response = payload

        if parsed['status'] == 'CONFIRMED':
            intent.status = 'CONFIRMED'
            intent.confirmed_at = timezone.now()
            intent.save()
            CollectionService._record_payment(intent)
        else:
            intent.status = 'FAILED'
            intent.error = parsed.get('error', '')
            intent.save()

        return intent

    @staticmethod
    def _record_payment(intent, user=None):
        """Convert a confirmed intent into a Payment + post to GL."""
        if intent.payment_id:
            return intent.payment

        if not intent.loan:
            logger.warning(f'Intent {intent.reference} has no loan — skipping payment.')
            return None

        from apps.payments.services_admin import record_payment

        # Resolve actor:
        #   1. explicit user (staff-initiated)
        #   2. loan officer
        #   3. approver
        #   4. org system user (portal-initiated — no staff in the loop)
        actor = user or intent.loan.loan_officer or intent.loan.approved_by
        if not actor:
            actor = CollectionService._get_system_user(intent.organization)
        if not actor:
            logger.warning(
                f'No actor (and no system user) for intent {intent.reference} — skipping.'
            )
            intent.error = 'No actor available to record payment.'
            intent.save(update_fields=['error'])
            return None

        try:
            payment, _ = record_payment(
                loan=intent.loan,
                amount=intent.amount,
                user=actor,
                payment_method=intent.provider_code,
                transaction_ref=intent.provider_txn_id or intent.reference,
                notes=f'Auto-recorded via MoMo: {intent.reference}',
            )
            intent.payment = payment
            intent.save(update_fields=['payment'])
            return payment
        except Exception as e:
            logger.exception(f'Failed to record payment for intent {intent.reference}: {e}')
            intent.error = str(e)
            intent.save(update_fields=['error'])
            return None

    @staticmethod
    def _get_system_user(org):
        """
        Return (creating if needed) a per-organization system user used to
        attribute payments that have no human actor — e.g. client-portal
        repayments where the borrower is the initiator.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()

        username = f'system@{org.code}'
        user = User.objects.filter(username=username).first()
        if user:
            return user

        user = User(
            username=username,
            first_name='System',
            last_name=f'Auto ({org.code})',
            is_active=True,
            is_staff=False,
        )
        if hasattr(user, 'organization_id'):
            user.organization = org
        user.set_unusable_password()
        user.save()
        logger.info(f'Created system user {username} for portal-attributed payments.')
        return user


# ============================================================
# Outbound (Disbursements)
# ============================================================
class DisbursementService:

    @staticmethod
    @transaction.atomic
    def initiate(org, client, amount, phone, provider_code,
                 loan=None, description='', user=None, branch=None):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive.')

        if branch is None:
            if client and getattr(client, 'branch_id', None):
                branch = client.branch
            elif loan and getattr(loan, 'branch_id', None):
                branch = loan.branch

        # Pass transaction_type='DISBURSEMENT'
        config = _get_config(org, provider_code, branch=branch, transaction_type='DISBURSEMENT')
        provider = get_provider(config)

        reference = _generate_reference(org, 'PAYOUT')

        intent = DisbursementIntent.objects.create(
            organization=org,
            branch=branch,
            client=client,
            loan=loan,
            provider_code=provider_code,
            reference=reference,
            amount=amount,
            phone=phone,
            status='PENDING',
            initiated_by=user,
            raw_request={
                'amount': str(amount),
                'phone': phone,
                'description': description,
                'provider': provider_code,
                'branch': branch.code if branch else None,
            },
        )
        try:
            result = provider.disburse(
                reference=reference,
                amount=amount,
                phone=phone,
                description=description,
            )
        except MomoProviderError as e:
            intent.status = 'FAILED'
            intent.error = str(e)
            intent.raw_response = e.raw
            intent.save()
            raise

        intent.provider_txn_id = result.get('provider_txn_id', '')
        intent.raw_response = result.get('raw', {})
        provider_status = result.get('status', 'PROCESSING')

        if provider_status == 'COMPLETED':
            intent.status = 'COMPLETED'
            intent.completed_at = timezone.now()
        elif provider_status == 'FAILED':
            intent.status = 'FAILED'
            intent.error = result.get('error', '')
        else:
            intent.status = 'PROCESSING'

        intent.save()
        return intent

    @staticmethod
    @transaction.atomic
    def process_webhook(provider_code, payload, headers, body_bytes, org=None):
        """Handle disbursement status update from provider."""
        if org:
            configs = MomoProviderConfig.objects.filter(
                organization=org, provider_code=provider_code, 
                is_active=True, 
                transaction_type='DISBURSEMENT' # <--- ADDED
            )
        else:
            configs = MomoProviderConfig.objects.filter(
                provider_code=provider_code, 
                is_active=True,
                transaction_type='DISBURSEMENT' # <--- ADDED
            )

        parsed = None
        intent = None
        for cfg in configs:
            provider = get_provider(cfg)
            try:
                if not provider.verify_webhook(headers, body_bytes):
                    continue
                parsed = provider.parse_webhook(payload)
                if parsed.get('provider_txn_id'):
                    intent = DisbursementIntent.objects.filter(
                        provider_code=provider_code,
                        provider_txn_id=parsed['provider_txn_id'],
                        organization=cfg.organization,
                    ).first()
                if intent:
                    break
            except Exception:
                continue

        if not intent:
            return None

        if intent.status in ('COMPLETED', 'FAILED', 'CANCELLED'):
            return intent

        intent.raw_response = payload
        if parsed['status'] == 'CONFIRMED':
            intent.status = 'COMPLETED'
            intent.completed_at = timezone.now()
        else:
            intent.status = 'FAILED'
            intent.error = parsed.get('error', '')
        intent.save()
        return intent