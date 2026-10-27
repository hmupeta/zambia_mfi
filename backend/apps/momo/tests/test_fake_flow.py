"""End-to-end tests for the fake provider flow."""
from decimal import Decimal

import pytest

from apps.clients.models import Client
from apps.momo.models import MomoProviderConfig, PaymentIntent
from apps.momo.services import CollectionService, DisbursementService


pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_config(org):
    return MomoProviderConfig.objects.create(
        organization=org,
        provider_code='FAKE',
        display_name='Fake Provider',
        is_active=True,
        is_sandbox=True,
        webhook_secret='test-secret',
    )


def test_collection_creates_payment_and_posts_gl(
    org, client, loan, hq_admin, gl_accounts, fake_config,
):
    intent = CollectionService.initiate(
        org=org, client=client, amount=250, phone=client.phone,
        provider_code='FAKE', loan=loan, user=hq_admin,
    )
    assert intent.status == 'CONFIRMED'
    assert intent.provider_txn_id.startswith('FAKE-')
    assert intent.payment is not None
    assert intent.payment.journal_entry is not None

    loan.refresh_from_db()
    assert loan.balance_due < Decimal('12400.00')


def test_collection_idempotent_on_repeat_confirm(
    org, client, loan, hq_admin, gl_accounts, fake_config,
):
    """Calling _record_payment twice should not create two payments."""
    intent = CollectionService.initiate(
        org=org, client=client, amount=100, phone=client.phone,
        provider_code='FAKE', loan=loan, user=hq_admin,
    )
    first_payment = intent.payment
    CollectionService._record_payment(intent, hq_admin)

    intent.refresh_from_db()
    assert intent.payment_id == first_payment.id


def test_disbursement_completes_immediately(
    org, client, loan, hq_admin, gl_accounts, fake_config,
):
    payout = DisbursementService.initiate(
        org=org, client=client, amount=500, phone=client.phone,
        provider_code='FAKE', loan=loan, user=hq_admin,
    )
    assert payout.status == 'COMPLETED'
    assert payout.provider_txn_id.startswith('FAKE-')


def test_missing_config_raises(org, client, loan):
    with pytest.raises(ValueError, match='No active config'):
        CollectionService.initiate(
            org=org, client=client, amount=100, phone=client.phone,
            provider_code='MTN_MOMO', loan=loan,
        )


def test_zero_amount_rejected(org, client, loan, fake_config):
    with pytest.raises(ValueError, match='positive'):
        CollectionService.initiate(
            org=org, client=client, amount=0, phone=client.phone,
            provider_code='FAKE', loan=loan,
        )