"""Tests for the loan application state machine."""
from decimal import Decimal
from datetime import date

import pytest

from apps.origination.models import (
    LoanApplication, WorkflowTemplate, WorkflowStage,
)
from apps.origination.services import ApplicationService, CreditScoringService


pytestmark = pytest.mark.django_db


@pytest.fixture
def workflow(db, org, loan_product):
    tpl = WorkflowTemplate.objects.create(
        organization=org, name='Standard', is_active=True, is_default=True,
    )
    WorkflowStage.objects.create(
        template=tpl, order=1, name='Review', role_required='LOAN_OFFICER',
        sla_hours=24,
    )
    WorkflowStage.objects.create(
        template=tpl, order=2, name='Approve', role_required='BRANCH_MANAGER',
        sla_hours=24, is_final=True,
    )
    return tpl


@pytest.fixture
def application(db, org, branch, client, loan_product, hq_admin, workflow):
    return LoanApplication.objects.create(
        organization=org, branch=branch, client=client,
        loan_product=loan_product,
        application_number='APP-TEST-0001',
        requested_amount=Decimal('10000'),
        requested_tenure_months=12,
        requested_repayment_frequency='MONTHLY',
        purpose='BUSINESS_CAPITAL',
        status='DRAFT',
        created_by=hq_admin,
        loan_officer=hq_admin,
    )


def test_credit_score_returns_grade(application):
    score, grade = CreditScoringService.score(application)
    assert 0 <= score <= 100
    assert grade in ('A', 'B', 'C', 'D')


def test_submit_moves_to_submitted(application, hq_admin):
    ApplicationService.submit(application, hq_admin)
    application.refresh_from_db()
    assert application.status == 'SUBMITTED'
    assert application.current_stage is not None


def test_advance_requires_different_user(application, hq_admin, branch_manager):
    """Submitting user cannot advance their own application."""
    ApplicationService.submit(application, hq_admin)
    # Rule 2 fires before Rule 3 — the creator cannot review at stage 1
    with pytest.raises(ValueError, match='[Ss]egregation of duties'):
        ApplicationService.advance(application, hq_admin)


def test_advance_to_final_stage_approves(application, hq_admin, branch_manager, loan_officer):
    ApplicationService.submit(application, hq_admin)
    # Different user advances
    ApplicationService.advance(application, loan_officer)
    application.refresh_from_db()
    assert application.status == 'UNDER_REVIEW'
    # Branch manager approves at final stage
    ApplicationService.advance(application, branch_manager)
    application.refresh_from_db()
    assert application.status == 'APPROVED'
    assert application.loan is not None
