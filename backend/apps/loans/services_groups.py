# apps/loans/services_groups.py
"""
Group lending services — registration, cycle management, collections,
cross-guarantee enforcement, and savings.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum, Q
from django.utils import timezone

from .models import (
    LoanGroup, LoanGroupMember, GroupMeeting, GroupAttendance, GroupCollection,
    SavingsTransaction,
)
from apps.clients.models import Client


# ============================================================
# Number generation
# ============================================================
def _generate_group_code(org):
    prefix = f'GRP-{org.code.upper()}-'
    last = (
        LoanGroup.objects
        .filter(organization=org, group_code__startswith=prefix)
        .aggregate(m=Max('group_code'))['m']
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f'{prefix}{seq:04d}'


def _generate_collection_number(org):
    today = timezone.now().strftime('%Y%m%d')
    prefix = f'GC-{org.code.upper()}-{today}-'
    last = (
        GroupCollection.objects
        .filter(organization=org, collection_number__startswith=prefix)
        .aggregate(m=Max('collection_number'))['m']
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f'{prefix}{seq:04d}'


# ============================================================
# Group Service
# ============================================================
class GroupService:

    # --------------------------------------------------------
    # Registration
    # --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_group(org, branch, name, leader_client, user,
                     meeting_frequency='WEEKLY', meeting_day='',
                     meeting_location='', notes='',
                     min_members=5, max_members=30):
        group = LoanGroup.objects.create(
            organization=org,
            branch=branch,
            group_name=name,
            group_code=_generate_group_code(org),
            leader=leader_client,
            status='FORMING',
            meeting_frequency=meeting_frequency,
            meeting_day=meeting_day,
            meeting_location=meeting_location,
            notes=notes,
            min_members=min_members,
            max_members=max_members,
            created_by=user,
        )
        # Add leader as a member with LEADER role
        LoanGroupMember.objects.create(
            loan_group=group,
            client=leader_client,
            role='LEADER',
            is_leader=True,
        )
        return group

    @staticmethod
    @transaction.atomic
    def add_member(group, client, user, role='MEMBER'):
        if group.status != 'FORMING':
            raise ValueError('Can only add members while the group is FORMING.')
        if group.member_count >= group.max_members:
            raise ValueError(f'Group has reached its maximum ({group.max_members} members).')
        if LoanGroupMember.objects.filter(loan_group=group, client=client, is_active=True).exists():
            raise ValueError('Client is already an active member of this group.')
        if client.kyc_status != 'VERIFIED':
            raise ValueError(f'Client {client} has not passed KYC verification.')

        member, _ = LoanGroupMember.objects.update_or_create(
            loan_group=group, client=client,
            defaults={'role': role, 'is_active': True, 'exited_at': None},
        )
        return member

    @staticmethod
    @transaction.atomic
    def remove_member(group, client, user, reason=''):
        try:
            member = LoanGroupMember.objects.get(
                loan_group=group, client=client, is_active=True,
            )
        except LoanGroupMember.DoesNotExist:
            raise ValueError('Client is not an active member of this group.')

        if member.is_leader:
            raise ValueError('Cannot remove the leader. Transfer leadership first.')
        if group.status == 'ACTIVE':
            # Check that member has no active loans
            from .models import Loan
            has_active = Loan.objects.filter(
                client=client, loan_group=group, is_fully_repaid=False,
            ).exists()
            if has_active:
                raise ValueError('Cannot remove member with active loans.')

        member.is_active = False
        member.exited_at = date.today()
        member.exit_reason = reason
        member.save()
        return member

    # --------------------------------------------------------
    # Cycle management
    # --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def start_cycle(group, user, duration_months=12):
        if group.status != 'FORMING':
            raise ValueError('Can only start a cycle while the group is FORMING.')
        if group.member_count < group.min_members:
            raise ValueError(
                f'Group needs at least {group.min_members} members to start. '
                f'Currently has {group.member_count}.'
            )

        today = date.today()
        group.status = 'ACTIVE'
        group.cycle_start_date = today
        group.cycle_end_date = today + timedelta(days=duration_months * 30)
        group.save(update_fields=['status', 'cycle_start_date', 'cycle_end_date', 'updated_at'])

        # Create the first meeting
        GroupService.schedule_meeting(
            group, scheduled_date=today + timedelta(days=7), user=user,
        )
        return group

    @staticmethod
    @transaction.atomic
    def close_cycle(group, user, notes=''):
        if group.status != 'ACTIVE':
            raise ValueError('Cycle is not active.')

        # Ensure all loans are repaid
        from .models import Loan
        active = Loan.objects.filter(loan_group=group, is_fully_repaid=False).count()
        if active > 0:
            raise ValueError(f'{active} loan(s) still outstanding. Cannot close cycle.')

        group.status = 'CLOSED'
        group.notes = (group.notes + '\n' + notes).strip()
        group.save(update_fields=['status', 'notes', 'updated_at'])
        return group

    # --------------------------------------------------------
    # Meetings
    # --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def schedule_meeting(group, scheduled_date, user=None, agenda=''):
        last = group.meetings.aggregate(m=Max('meeting_number'))['m'] or 0
        return GroupMeeting.objects.create(
            loan_group=group,
            meeting_number=last + 1,
            scheduled_date=scheduled_date,
            agenda=agenda,
            created_by=user,
        )

    @staticmethod
    @transaction.atomic
    def record_attendance(meeting, member_ids, user):
        """
        member_ids: list of member UUIDs present.
        """
        member_ids_set = set(str(i) for i in member_ids)
        for member in meeting.loan_group.active_members:
            is_present = str(member.id) in member_ids_set
            GroupAttendance.objects.update_or_create(
                meeting=meeting, member=member,
                defaults={'is_present': is_present},
            )
        meeting.attendance_count = len(member_ids_set)
        meeting.status = 'HELD'
        meeting.actual_date = date.today()
        meeting.save(update_fields=['attendance_count', 'status', 'actual_date'])
        return meeting

    # --------------------------------------------------------
    # Collections — THE core feature
    # --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def record_collection(group, collections_data, user,
                          channel='CASH', reference='', notes='', meeting=None):
        """
        Record a group collection: one receipt covering N members.

        collections_data: [
            {'member_id': <LoanGroupMember UUID>, 'amount': Decimal(...)},
            {'member_id': <...>, 'amount': Decimal(...)},
        ]

        Returns the GroupCollection parent record.
        """
        if group.status != 'ACTIVE':
            raise ValueError('Group is not active — cannot collect.')

        from .models import Loan
        from apps.payments.services_admin import record_payment

        # Validate & total
        parsed = []
        total = Decimal('0')
        for entry in collections_data:
            amount = Decimal(str(entry['amount']))
            if amount <= 0:
                continue
            parsed.append((entry['member_id'], amount))
            total += amount

        if total <= 0:
            raise ValueError('No valid amounts to collect.')

        # Create parent record
        collection = GroupCollection.objects.create(
            organization=group.organization,
            loan_group=group,
            meeting=meeting,
            collection_number=_generate_collection_number(group.organization),
            amount=total,
            channel=channel,
            reference=reference,
            notes=notes,
            created_by=user,
        )

        # Apply each member's share to their active loan
        allocations_count = 0
        for member_id, amount in parsed:
            try:
                member = LoanGroupMember.objects.get(
                    id=member_id, loan_group=group, is_active=True,
                )
            except LoanGroupMember.DoesNotExist:
                continue

            loan = (
                Loan.objects
                .filter(client=member.client, loan_group=group, is_fully_repaid=False)
                .order_by('created_at')
                .first()
            )
            if not loan:
                # Member has no active loan — treat as savings
                member.savings_balance = Decimal(member.savings_balance or 0) + amount
                member.save(update_fields=['savings_balance'])
                continue

            try:
                payment, _ = record_payment(
                    loan=loan,
                    amount=amount,
                    user=user,
                    payment_method=channel,
                    transaction_ref=reference,
                    notes=f'Group collection {collection.collection_number}',
                )
                payment.group_collection = collection
                payment.save(update_fields=['group_collection'])
                allocations_count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f'Group collection payment failed for {member.client}: {e}'
                )

        collection.member_count = allocations_count
        collection.save(update_fields=['member_count'])

        # Update meeting totals if attached
        if meeting:
            meeting.collections_received = (
                Decimal(meeting.collections_received or 0) + total
            )
            meeting.save(update_fields=['collections_received'])

        return collection

    # --------------------------------------------------------
    # Savings - New addition
    # --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def record_savings(group, savings_data, user, channel='CASH', reference=''):
        """
        Record weekly savings deposits for group members.
        savings_data = [{'member_id': uuid, 'amount': 100}, ...]
        """
        from apps.accounting.models import GLAccount
        from apps.accounting.services import AccountingService

        total_deposited = Decimal('0')
        valid_txns = []

        # 1. Update Member Balances and create ledger entries
        for item in savings_data:
            amount = Decimal(str(item['amount']))
            if amount <= 0:
                continue
                
            member = group.members.select_for_update().get(id=item['member_id'])
            member.savings_balance += amount
            member.save(update_fields=['savings_balance'])
            
            txn = SavingsTransaction.objects.create(
                organization=group.organization,
                branch=group.branch,
                client=member.client,
                loan_group=group,
                transaction_type='DEPOSIT',
                amount=amount,
                reference=reference,
                created_by=user
            )
            valid_txns.append(txn)
            total_deposited += amount

        if total_deposited == 0:
            return

        # 2. Update Group Pool
        group.savings_balance += total_deposited
        group.save(update_fields=['savings_balance'])

        # 3. Post GL Entry
        # DR Cash/Bank (1010/1020) / CR Member Savings Liability (2100)
        debit_code = {'CASH': '1010', 'BANK': '1020', 'MTN_MOMO': '1030', 'AIRTEL_MONEY': '1030'}.get(channel, '1010')
        debit_acc = GLAccount.objects.filter(organization=group.organization, code=debit_code, is_active=True).first()
        credit_acc = GLAccount.objects.filter(organization=group.organization, code__startswith='21', is_active=True).first()

        if debit_acc and credit_acc:
            AccountingService.create_journal_entry(
                organization=group.organization,
                entry_date=timezone.now().date(),
                reference=f'SAV-{group.group_code or group.id.hex[:6]}-{timezone.now().strftime("%y%m%d")}',
                description=f'Group savings deposit for {group.group_name}',
                lines=[
                    {'account_code': debit_acc.code, 'debit': float(total_deposited), 'credit': 0, 'memo': f'Savings via {channel}'},
                    {'account_code': credit_acc.code, 'debit': 0, 'credit': float(total_deposited), 'memo': 'Member savings liability'},
                ],
                source_type='Savings',
                source_id=group.id,
                branch=group.branch,
                user=user,
            )

        return total_deposited

    # --------------------------------------------------------
    # Analytics
    # --------------------------------------------------------
    @staticmethod
    def group_summary(group):
        """
        Return a dict with group-level KPIs:
        member count, portfolio, PAR, savings, on-time rate.
        """
        from .models import Loan, LoanInstallment

        today = date.today()
        loans = Loan.objects.filter(loan_group=group)
        active_loans = loans.filter(is_fully_repaid=False)

        portfolio = active_loans.aggregate(s=Sum('balance_due'))['s'] or 0

        # PAR 30 — installments overdue > 30 days
        cutoff = today - timedelta(days=30)
        par_installments = LoanInstallment.objects.filter(
            loan__in=active_loans,
            is_paid=False,
            due_date__lt=cutoff,
        )
        par_outstanding = sum(
            (inst.total_due - inst.paid_amount) for inst in par_installments
        ) or Decimal('0')

        par_ratio = (float(par_outstanding) / float(portfolio) * 100) if portfolio else 0

        # Collection rate
        from apps.payments.models import Payment
        total_collected = Payment.objects.filter(
            organization=group.organization,
            loan__loan_group=group,
            is_reversed=False,
        ).aggregate(s=Sum('amount'))['s'] or 0

        total_disbursed = loans.aggregate(s=Sum('disbursed_amount'))['s'] or 0

        return {
            'member_count': group.member_count,
            'active_loans': active_loans.count(),
            'portfolio': float(portfolio),
            'total_disbursed': float(total_disbursed),
            'total_collected': float(total_collected),
            'par_outstanding': float(par_outstanding),
            'par_ratio': round(par_ratio, 2),
            'savings_balance': float(group.savings_balance or 0),
            'cycle_number': group.cycle_number,
            'cycle_start': str(group.cycle_start_date) if group.cycle_start_date else None,
            'cycle_end': str(group.cycle_end_date) if group.cycle_end_date else None,
        }