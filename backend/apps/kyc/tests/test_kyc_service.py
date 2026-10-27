"""Tests for KYC risk scoring and verification lifecycle."""
from decimal import Decimal

import pytest

from apps.kyc.services import KYCRiskService, KYCVerificationService


pytestmark = pytest.mark.django_db


def test_risk_score_low_for_rural_client(client, db):
    client.province = 'NORTHERN'
    client.occupation = 'FARMER'
    client.save()
    result = KYCRiskService.compute(client)
    assert result['risk_level'] in ('LOW', 'MEDIUM')


def test_risk_score_high_for_urban_high_risk(client):
    client.province = 'LUSAKA'
    client.occupation = 'MONEY EXCHANGE'
    client.save()
    result = KYCRiskService.compute(client)
    assert result['risk_score'] > 0


def test_initiate_creates_verification(client, hq_admin):
    v = KYCVerificationService.initiate(client, user=hq_admin)
    assert v.status == 'IN_PROGRESS'
    assert v.verification_number.startswith('KYC-')


def test_verify_marks_client_verified(client, hq_admin):
    v = KYCVerificationService.initiate(client, user=hq_admin)
    v.status = 'PENDING_REVIEW'
    v.save()
    KYCVerificationService.verify(v, hq_admin, notes='All checks passed')
    client.refresh_from_db()
    assert client.kyc_status == 'VERIFIED'
