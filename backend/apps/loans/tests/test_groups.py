"""Tests for group lending services."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.loans.models import LoanGroup, LoanGroupMember, GroupCollection
from apps.loans.services_groups import GroupService


pytestmark = pytest.mark.django_db


@pytest.fixture
def client2(db, org, branch, hq_admin):
    from apps.clients.models import Client
    return Client.objects.create(
        organization=org, branch=branch,
        nrc='223456/11/1', first_name='Jane', last_name='Smith',
        gender='F', phone='0971111111', kyc_status='VERIFIED',
        created_by=hq_admin,
    )


def test_create_group_adds_leader_as_member(org, branch, client, hq_admin):
    group = GroupService.create_group(
        org=org, branch=branch, name='Test Group',
        leader_client=client, user=hq_admin,
    )
    assert group.status == 'FORMING'
    assert group.group_code.startswith('GRP-TEST-')
    assert group.member_count == 1


def test_add_member_requires_kyc(client2, org, branch, client, hq_admin):
    group = GroupService.create_group(
        org=org, branch=branch, name='KYC Group',
        leader_client=client, user=hq_admin,
    )
    member = GroupService.add_member(group, client2, hq_admin)
    assert member.is_active is True
    assert group.member_count == 2


def test_start_cycle_requires_min_members(org, branch, client, hq_admin):
    group = GroupService.create_group(
        org=org, branch=branch, name='Small Group',
        leader_client=client, user=hq_admin, min_members=5,
    )
    with pytest.raises(ValueError, match='at least'):
        GroupService.start_cycle(group, hq_admin)


def test_start_cycle_activates_group(org, branch, client, hq_admin):
    group = GroupService.create_group(
        org=org, branch=branch, name='Active Group',
        leader_client=client, user=hq_admin, min_members=1,
    )
    GroupService.start_cycle(group, hq_admin)
    group.refresh_from_db()
    assert group.status == 'ACTIVE'
    assert group.cycle_start_date == date.today()
    assert group.meetings.count() == 1


def test_record_collection_creates_parent_and_payments(
    org, branch, client, client2, loan, loan_product, hq_admin, gl_accounts,
):
    """A group collection should create one parent + N payments."""
    # Set up group with two members
    group = GroupService.create_group(
        org=org, branch=branch, name='Collection Group',
        leader_client=client, user=hq_admin, min_members=1,
    )
    GroupService.add_member(group, client2, hq_admin)
    GroupService.start_cycle(group, hq_admin)

    # Attach client's existing loan to the group
    loan.loan_group = group
    loan.save(update_fields=['loan_group'])

    # Create a second loan for client2 WITH installments
    from apps.loans.models import Loan, LoanInstallment
    loan2 = Loan.objects.create(
        organization=org, branch=branch, client=client2, loan_product=loan_product,
        loan_number='LN-TEST-0002',
        amount=Decimal('5000'), total_interest=Decimal('1000'),
        total_amount_due=Decimal('6000'), disbursed_amount=Decimal('5000'),
        balance_due=Decimal('6000'),
        start_date=date.today(), maturity_date=date.today() + timedelta(days=180),
        interest_rate=Decimal('20'), interest_method='FLAT',
        repayment_frequency='MONTHLY', status='DISBURSED',
        loan_group=group,
    )
    # Create installments so allocation can happen
    for i in range(1, 4):
        LoanInstallment.objects.create(
            loan=loan2,
            installment_no=i,
            due_date=date.today() + timedelta(days=30 * i),
            principal_amount=Decimal('1666.67'),
            interest_amount=Decimal('333.33'),
            penalty_amount=Decimal('0'),
            total_due=Decimal('2000.00'),
            paid_amount=Decimal('0'),
            is_paid=False,
            status='PENDING',
        )

    # Get the members
    member1 = group.members.get(client=client)
    member2 = group.members.get(client=client2)

    # Record collection of K500 + K500 = K1000
    collection = GroupService.record_collection(
        group=group,
        collections_data=[
            {'member_id': str(member1.id), 'amount': Decimal('500')},
            {'member_id': str(member2.id), 'amount': Decimal('500')},
        ],
        user=hq_admin,
        channel='CASH',
    )

    assert collection.amount == Decimal('1000')
    assert collection.member_count == 2
    assert collection.payments.count() == 2

    # Loans should both have decreased
    loan.refresh_from_db()
    loan2.refresh_from_db()
    assert loan.balance_due < Decimal('12400.00')
    assert loan2.balance_due < Decimal('6000')