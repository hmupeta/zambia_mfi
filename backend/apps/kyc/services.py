# apps/kyc/services.py
from datetime import timedelta, date
from decimal import Decimal
import secrets

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.conf import settings

from .models import (
    KYCVerification, KYCDocument, KYCCheck, KYCRiskAssessment,
    KYCReviewSchedule, KYCDocumentRequirement, KYCSelfServiceToken,
    KYC_STATUS_CHOICES, KYC_RISK_LEVEL_CHOICES,
)
from .providers import get_provider


# ============================================================
# Number Generator
# ============================================================
class KYCNumberService:
    @staticmethod
    def generate(organization):
        today = timezone.now().date()
        prefix = f'KYC-{organization.code.upper()}-{today.strftime("%Y%m%d")}'
        last = (
            KYCVerification.objects
            .filter(organization=organization, verification_number__startswith=prefix)
            .aggregate(m=Max('verification_number')).get('m')
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'{prefix}-{seq:04d}'


# ============================================================
# Risk Assessment Engine
# ============================================================
class KYCRiskService:
    """
    Computes a risk score based on client data. Real-world implementations
    would factor in geography, occupation, transaction patterns, PEP lists.
    """

    @staticmethod
    def compute(client, verification=None):
        score = 0
        factors = {}

        # Geographic risk — rural areas are lower risk for KYC per BoZ guidance
        province = (client.province or '').upper()
        if province in ('LUSAKA', 'COPPERBELT'):
            score += 10
            factors['urban_location'] = 10

        # Occupation risk
        high_risk_occ = ['MINING', 'CASH TRADER', 'MONEY EXCHANGE', 'FX']
        occ = (client.occupation or '').upper()
        if any(k in occ for k in high_risk_occ):
            score += 25
            factors['high_risk_occupation'] = 25

        # Age: minors raise concern
        if client.date_of_birth:
            age = (date.today() - client.date_of_birth).days // 365
            if age < 21:
                score += 15
                factors['young_age'] = 15

        # Missing email or phone
        if not client.email:
            score += 5
            factors['no_email'] = 5

        # Determine level
        if score >= 50:
            level = 'HIGH'
        elif score >= 25:
            level = 'MEDIUM'
        else:
            level = 'LOW'

        # Run PEP / sanctions screening
        is_pep = False
        is_sanctioned = False
        pep_details = ''
        sanction_details = ''

        provider = get_provider()
        try:
            full_name = f'{client.first_name} {client.last_name}'
            pep_result = provider.screen_pep(full_name)
            is_pep = pep_result.get('result') == 'MATCH'
            if is_pep:
                pep_details = str(pep_result.get('matches', []))

            aml_result = provider.screen_aml(full_name, client.nrc or '')
            is_sanctioned = aml_result.get('result') == 'MATCH'
            if is_sanctioned:
                sanction_details = str(aml_result.get('matches', []))
        except Exception:
            pass  # Screening failure shouldn't block assessment

        if is_pep:
            level = 'PEP'
            score = max(score, 75)
            factors['pep'] = 25
        if is_sanctioned:
            level = 'HIGH'
            score = max(score, 100)
            factors['sanctions_hit'] = 50

        requires_edd = level in ('HIGH', 'PEP')

        return {
            'risk_level': level,
            'risk_score': min(score, 100),
            'is_pep': is_pep,
            'pep_details': pep_details,
            'is_sanctioned': is_sanctioned,
            'sanctions_details': sanction_details,
            'requires_edd': requires_edd,
            'factors': factors,
        }


# ============================================================
# Verification Service — main workflow
# ============================================================
class KYCVerificationService:

    @staticmethod
    @transaction.atomic
    def initiate(client, user=None, client_type='INDIVIDUAL'):
        """Start a new verification for a client."""
        # If there's an open verification, return it
        existing = KYCVerification.objects.filter(
            client=client, status__in=['NOT_STARTED', 'IN_PROGRESS', 'PENDING_REVIEW'],
        ).first()
        if existing:
            return existing

        return KYCVerification.objects.create(
            organization=client.organization,
            client=client,
            verification_number=KYCNumberService.generate(client.organization),
            client_type=client_type,
            status='IN_PROGRESS',
            initiated_by=user,
        )

    @staticmethod
    @transaction.atomic
    def run_checks(verification, id_type, id_number, full_name, dob, address='',
                   id_photo=None, selfie_photo=None):
        """
        Run all supported automated checks. Marks verification PENDING_REVIEW when done.
        """
        provider = get_provider()

        # 1. ID Number Verification
        id_result = provider.verify_id(id_type, id_number, full_name, dob)
        KYCCheck.objects.create(
            verification=verification,
            check_type='ID_NUMBER',
            provider=provider.name,
            result=id_result.get('result', 'FAIL'),
            reference=id_result.get('reference', ''),
            confidence_score=id_result.get('confidence_score'),
            raw_response=id_result.get('raw_response'),
        )

        # 2. OCR (extract fields)
        if id_photo:
            KYCCheck.objects.create(
                verification=verification,
                check_type='OCR',
                provider=provider.name,
                result='PASS',
                raw_response={'extracted': {
                    'full_name': full_name,
                    'id_number': id_number,
                }},
            )

        # 3. Face match
        if id_photo and selfie_photo:
            face_result = provider.verify_face(id_photo, selfie_photo)
            KYCCheck.objects.create(
                verification=verification,
                check_type='FACE_MATCH',
                provider=provider.name,
                result=face_result.get('result', 'FAIL'),
                raw_response=face_result.get('raw_response'),
            )

        # 4. AML screening
        aml_result = provider.screen_aml(full_name, id_number)
        KYCCheck.objects.create(
            verification=verification,
            check_type='AML',
            provider=provider.name,
            result=aml_result.get('result', 'PASS'),
            raw_response=aml_result.get('raw_response'),
        )

        # 5. PEP screening
        pep_result = provider.screen_pep(full_name)
        KYCCheck.objects.create(
            verification=verification,
            check_type='PEP',
            provider=provider.name,
            result=pep_result.get('result', 'PASS'),
            raw_response=pep_result.get('raw_response'),
        )

        # Snapshot submitted data
        verification.submitted_id_type = id_type
        verification.submitted_id_number = id_number
        verification.submitted_full_name = full_name
        verification.submitted_dob = dob
        verification.submitted_address = address  # <--- ADDED THIS
        verification.submitted_at = timezone.now()
        verification.status = 'PENDING_REVIEW'
        verification.save()

        # Run risk assessment
        KYCVerificationService.assess_risk(verification)
        return verification

    @staticmethod
    @transaction.atomic
    def assess_risk(verification):
        result = KYCRiskService.compute(verification.client, verification)
        KYCRiskAssessment.objects.update_or_create(
            verification=verification,
            defaults=result,
        )
        return verification.risk_assessment

    @staticmethod
    @transaction.atomic
    def verify(verification, user, notes=''):
        """Mark a verification as fully verified."""
        if verification.status not in ('PENDING_REVIEW', 'IN_PROGRESS'):
            raise ValueError(f'Cannot verify: status is {verification.status}.')

        verification.status = 'VERIFIED'
        verification.reviewed_by = user
        verification.reviewed_at = timezone.now()
        verification.verified_at = timezone.now()
        verification.review_notes = notes

        # Compute expiry based on risk level
        risk = getattr(verification, 'risk_assessment', None)
        freq_map = (getattr(settings, 'KYC', {}) or {}).get('REVIEW_FREQUENCY_MONTHS', {})
        months = freq_map.get(risk.risk_level if risk else 'LOW', 12)
        verification.expires_at = date.today() + timedelta(days=months * 30)
        verification.save()

        # Update client KYC status
        client = verification.client
        client.kyc_status = 'VERIFIED'
        client.save(update_fields=['kyc_status'])

        # Create review schedule
        KYCReviewSchedule.objects.update_or_create(
            client=client,
            defaults={
                'last_reviewed_at': date.today(),
                'next_review_due': verification.expires_at,
                'risk_level': risk.risk_level if risk else 'LOW',
                'review_frequency_months': months,
                'is_active': True,
            },
        )

        # ─── NOTIFICATION TRIGGER ───────────────────────────────
        # Send KYC approval SMS/WhatsApp/Email to the client
        try:
            from apps.notifications.triggers import on_kyc_approved
            on_kyc_approved(client, user=user)
        except Exception:
            pass

        return verification

    @staticmethod
    @transaction.atomic
    def reject(verification, user, reason=''):
        if verification.status not in ('PENDING_REVIEW', 'IN_PROGRESS'):
            raise ValueError(f'Cannot reject: status is {verification.status}.')

        verification.status = 'REJECTED'
        verification.reviewed_by = user
        verification.reviewed_at = timezone.now()
        verification.rejection_reason = reason
        verification.save()

        client = verification.client
        client.kyc_status = 'REJECTED'
        client.save(update_fields=['kyc_status'])
        return verification


# ============================================================
# Document Requirements Resolver
# ============================================================
class KYCDocumentService:

    @staticmethod
    def required_for(client_type, risk_level='LOW'):
        """Returns the list of requirements that apply."""
        reqs = KYCDocumentRequirement.objects.filter(
            is_active=True, client_type=client_type,
        )
        # Filter by risk level
        out = []
        for r in reqs:
            allowed = r.required_for_risk_levels or []
            if not allowed or risk_level in allowed or 'ALL' in allowed:
                out.append(r)
        return out

    @staticmethod
    def completion_status(verification):
        reqs = KYCDocumentService.required_for(
            verification.client_type,
            getattr(verification, 'risk_assessment', None).risk_level
            if hasattr(verification, 'risk_assessment') else 'LOW',
        )
        submitted_types = set(
            verification.documents.values_list('document_type', flat=True)
        )
        return {
            'total_required': len(reqs),
            'submitted': sum(1 for r in reqs if r.document_type in submitted_types),
            'missing': [r.document_type for r in reqs
                        if r.is_mandatory and r.document_type not in submitted_types],
        }


# ============================================================
# Self-Service Token Service
# ============================================================
class KYCSelfServiceTokenService:

    @staticmethod
    def generate(client, user=None, valid_hours=72):
        token = secrets.token_urlsafe(48)
        return KYCSelfServiceToken.objects.create(
            client=client,
            token=token,
            expires_at=timezone.now() + timedelta(hours=valid_hours),
            created_by=user,
        )

    @staticmethod
    def consume(token_str, ip_address=None):
        try:
            token = KYCSelfServiceToken.objects.get(token=token_str)
        except KYCSelfServiceToken.DoesNotExist:
            raise ValueError('Invalid token.')

        if token.is_used:
            raise ValueError('Token already used.')
        if token.expires_at < timezone.now():
            raise ValueError('Token expired.')

        token.is_used = True
        token.used_at = timezone.now()
        token.ip_address = ip_address
        token.save()
        return token