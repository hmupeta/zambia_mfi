from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging

from django.db import transaction
from django.utils import timezone

from apps.loans.models import Loan
from apps.loans.services import LoanService

from .models import (
    LoanApplication, WorkflowTemplate, WorkflowStage,
    ApplicationTransition, Task, TaskComment,
)

logger = logging.getLogger(__name__)


# ============================================================
# Application Number Generator
# ============================================================
class ApplicationNumberService:

    @staticmethod
    def generate(organization):
        today = timezone.now().date()
        prefix = f'APP-{organization.code.upper()}-{today.strftime("%Y%m%d")}'
        from django.db.models import Max
        last = (
            LoanApplication.objects
            .filter(organization=organization, application_number__startswith=prefix)
            .aggregate(m=Max('application_number'))
            .get('m')
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'{prefix}-{seq:04d}'


# ============================================================
# Workflow resolution + stage advancement
# ============================================================
class WorkflowService:

    @staticmethod
    def resolve_template(organization, loan_product, amount):
        """
        Pick the best matching workflow template for the application.
        Priority: exact product + amount range → product only → default.
        """
        qs = WorkflowTemplate.objects.filter(
            organization=organization, is_active=True,
        ).order_by('name')

        # 1. Product-specific + amount range
        match = qs.filter(
            loan_product=loan_product,
            min_amount__lte=amount,
            max_amount__gte=amount,
        ).first()
        if match:
            return match

        # 2. Product-specific (no amount constraints)
        match = qs.filter(
            loan_product=loan_product, min_amount__isnull=True, max_amount__isnull=True,
        ).first()
        if match:
            return match

        # 3. Default
        return qs.filter(is_default=True).first()

    @staticmethod
    def first_stage(template):
        return template.stages.order_by('order').first() if template else None

    @staticmethod
    def next_stage(template, current_stage):
        if not template or not current_stage:
            return None
        return (
            template.stages
            .filter(order__gt=current_stage.order)
            .order_by('order')
            .first()
        )

    @staticmethod
    def create_stage_task(application, stage, actor=None):
        """
        Create a Task for the user(s) who need to act on this stage.
        Assigns to the branch manager when stage requires it.
        """
        if not stage:
            return None

        from apps.core.models import User

        assignee = None

        if stage.role_required == 'BRANCH_MANAGER':
            assignee = User.objects.filter(
                organization=application.organization,
                branch=application.branch,
                role='BRANCH_MANAGER',
                is_active=True,
            ).first()
        elif stage.role_required == 'HQ_ADMIN':
            assignee = User.objects.filter(
                organization=application.organization,
                role='HQ_ADMIN',
                is_active=True,
            ).first()
        elif stage.role_required == 'LOAN_OFFICER':
            assignee = application.loan_officer

        if not assignee:
            return None

        due = timezone.now() + timedelta(hours=stage.sla_hours)

        return Task.objects.create(
            organization=application.organization,
            branch=application.branch,
            title=f'Review {application.application_number} — {stage.name}',
            description=(
                f'{application.client} has requested '
                f'{application.requested_amount} for '
                f'{application.requested_tenure_months} months.'
            ),
            assigned_to=assignee,
            created_by=actor,
            related_type='LOAN_APPLICATION',
            related_id=application.id,
            priority='HIGH' if stage.sla_hours <= 24 else 'NORMAL',
            due_date=due,
        )


# ============================================================
# Credit scoring (basic engine; pluggable later)
# ============================================================
class CreditScoringService:
    """
    Simple rule-based scoring. Returns (score, grade).
    Real implementations could call a CRB or ML model.
    """

    @staticmethod
    def score(application):
        score = 50  # starting baseline

        income = application.monthly_income or Decimal('0')
        expenses = application.monthly_expenses or Decimal('0')
        debts = application.existing_debts or Decimal('0')
        net_worth = application.net_worth or Decimal('0')
        requested = application.requested_amount or Decimal('0')

        net_monthly = income - expenses

        # Debt-to-income
        if income > 0:
            dti = (expenses + debts) / income
            if dti < Decimal('0.3'):
                score += 20
            elif dti < Decimal('0.5'):
                score += 10
            elif dti < Decimal('0.7'):
                score -= 5
            else:
                score -= 20

        # Net worth coverage of requested amount
        if requested > 0:
            coverage = net_worth / requested
            if coverage >= Decimal('1.5'):
                score += 15
            elif coverage >= Decimal('0.75'):
                score += 8
            elif coverage < Decimal('0.25'):
                score -= 10

        # Positive net income
        if net_monthly > 0:
            score += 10
        else:
            score -= 15

        # Clamp
        score = max(0, min(100, score))

        if score >= 80:
            grade = 'A'
        elif score >= 65:
            grade = 'B'
        elif score >= 45:
            grade = 'C'
        else:
            grade = 'D'

        return score, grade


# ============================================================
# Application Service — main workflow
# ============================================================
class ApplicationService:
    # ============================================================
    # Segregation of Duties — Four-Eyes Principle
    # ============================================================
    @staticmethod
    def _check_segregation(application, user, stage=None):
        """
        Enforce separation of duties on loan applications.

        Rules:
          1. The user who SUBMITTED the application cannot APPROVE it.
          2. The user who CREATED the application cannot act on STAGE 1.
          3. The user who performed the LAST action cannot perform the NEXT action.

        Raises ValueError with a clear message if any rule is violated.
        """
        # Rule 1 — Submitter cannot approve
        if stage and stage.is_final:
            if application.submitted_by_id and application.submitted_by_id == user.id:
                raise ValueError(
                    'Segregation of duties: the user who submitted this '
                    'application cannot also approve it. A different '
                    'authorized user must approve.'
                )

        # Rule 2 — Creator cannot review at Stage 1
        if stage and stage.order == 1:
            if application.created_by_id and application.created_by_id == user.id:
                raise ValueError(
                    'Segregation of duties: the user who created this '
                    'application cannot review it at the first stage. '
                    'A different officer must review.'
                )

        # Rule 3 — No consecutive actions by the same user
        last_transition = application.transitions.order_by('-created_at').first()
        if last_transition and last_transition.user_id == user.id:
            raise ValueError(
                f'Segregation of duties: you already performed the last '
                f'action ("{last_transition.action}"). A different user '
                f'must take the next step.'
            )

    @staticmethod
    @transaction.atomic
    def submit(application, user, comments=''):
        if application.status not in ('DRAFT', 'RETURNED'):
            raise ValueError(f'Cannot submit: status is {application.status}.')

        # Resolve workflow if not yet set
        if not application.workflow_template:
            template = WorkflowService.resolve_template(
                application.organization,
                application.loan_product,
                application.requested_amount,
            )
            if not template:
                raise ValueError(
                    'No workflow template found. Configure one for this product/amount.'
                )
            application.workflow_template = template

        stage = WorkflowService.first_stage(application.workflow_template)
        if not stage:
            raise ValueError('Workflow template has no stages.')

        # Staff-submitted applications skip the loan officer review stage:
        # when a loan officer submits, that submission IS the officer review.
        # Only client-portal applications (submitted by the org system user)
        # require a distinct LO review before the branch manager sees them.
        if (
            stage.role_required == 'LOAN_OFFICER'
            and getattr(user, 'role', None) == 'LOAN_OFFICER'
        ):
            next_stage = WorkflowService.next_stage(
                application.workflow_template, stage
            )
            if next_stage:
                stage = next_stage

        # Auto-score
        score, grade = CreditScoringService.score(application)
        application.credit_score = score
        application.credit_score_grade = grade

        application.status = 'SUBMITTED'
        application.current_stage = stage
        application.submitted_by = user
        application.submitted_at = timezone.now()
        application.save()

        ApplicationTransition.objects.create(
            application=application, from_stage=None, to_stage=stage,
            action='SUBMITTED', user=user, comments=comments,
        )
        WorkflowService.create_stage_task(application, stage, actor=user)
        return application

    @staticmethod
    @transaction.atomic
    def advance(application, user, comments=''):
        """
        Move to the next stage. If the current stage is final, approve the application.
        """
        if application.status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValueError(f'Cannot advance: status is {application.status}.')

        current = application.current_stage
        if not current:
            raise ValueError('Application has no current stage.')

        # Permission check
        if user.role != current.role_required and user.role != 'HQ_ADMIN' and not user.is_superuser:
            raise ValueError(
                f'Your role ({user.role}) cannot act on stage "{current.name}" '
                f'(requires {current.role_required}).'
            )

        # Segregation of duties check
        ApplicationService._check_segregation(application, user, stage=current)

        # If this stage is final, approve
        if current.is_final:
            return ApplicationService._approve(application, user, comments)

        next_stage = WorkflowService.next_stage(application.workflow_template, current)
        if not next_stage:
            return ApplicationService._approve(application, user, comments)

        application.current_stage = next_stage
        application.status = 'UNDER_REVIEW'
        application.save()

        ApplicationTransition.objects.create(
            application=application, from_stage=current, to_stage=next_stage,
            action='MOVED', user=user, comments=comments,
        )
        Task.objects.filter(
            related_type='LOAN_APPLICATION', related_id=application.id,
            status__in=['OPEN', 'IN_PROGRESS'],
        ).update(status='COMPLETED', completed_at=timezone.now())

        WorkflowService.create_stage_task(application, next_stage, actor=user)
        return application

    @staticmethod
    @transaction.atomic
    def _approve(application, user, comments):
        # ---- Fail-safe: enforce Rule 1 one more time ----
        if application.submitted_by_id == user.id:
            raise ValueError(
                'Segregation of duties: the submitter cannot approve. '
                'A different manager or committee member must approve.'
            )
        if application.created_by_id == user.id and application.created_by_id == application.submitted_by_id:
            raise ValueError(
                'Segregation of duties: the creator-submitter cannot approve. '
                'A different authorized user must approve.'
            )

        application.status = 'APPROVED'
        application.decided_by = user
        application.decided_at = timezone.now()
        application.decision_notes = comments
        application.save()
        ApplicationTransition.objects.create(
            application=application,
            from_stage=application.current_stage, to_stage=None,
            action='APPROVED', user=user, comments=comments,
        )

        # Create the Loan record in APPROVED status
        application = ApplicationService._create_loan(application, user)

        # Create a follow-up task to disburse
        if application.loan:
            Task.objects.create(
                organization=application.organization,
                branch=application.branch,
                title=f'Disburse loan {application.loan.loan_number}',
                description=f'{application.client} · {application.loan.amount}',
                assigned_to=user,
                related_type='LOAN',
                related_id=application.loan.id,
                priority='HIGH',
            )

        # ─── NOTIFICATION TRIGGER ───────────────────────────────
        # Send approval SMS/WhatsApp/Email to the client
        try:
            from apps.notifications.triggers import on_application_approved
            on_application_approved(application, user=user)
        except Exception:
            pass

        return application

    @staticmethod
    def _create_loan(application, user):
        """Instantiate a Loan from the approved application."""
        if application.loan_id:
            return application

        start = timezone.now().date()
        maturity = start + timedelta(days=application.requested_tenure_months * 30)

        loan_number = f'LN-{application.organization.code.upper()}-{start.strftime("%Y%m%d")}-{application.application_number[-4:]}'

        loan = Loan.objects.create(
            organization=application.organization,
            loan_number=loan_number,
            branch=application.branch,
            client=application.client,
            loan_product=application.loan_product,
            loan_officer=application.loan_officer,
            approved_by=user,
            amount=application.requested_amount,
            total_interest=Decimal('0'),
            total_amount_due=Decimal('0'),
            balance_due=Decimal('0'),
            start_date=start,
            maturity_date=maturity,
            interest_rate=application.loan_product.interest_rate,
            interest_method=application.loan_product.interest_method,
            repayment_frequency=application.requested_repayment_frequency or application.loan_product.repayment_frequency,
            status='APPROVED',
        )
        LoanService.generate_installments(loan)
        application.loan = loan
        application.save(update_fields=['loan'])
        return application

    @staticmethod
    @transaction.atomic
    def reject(application, user, comments=''):
        if application.status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValueError(f'Cannot reject: status is {application.status}.')

        application.status = 'REJECTED'
        application.decided_by = user
        application.decided_at = timezone.now()
        application.decision_notes = comments
        application.save()

        ApplicationTransition.objects.create(
            application=application,
            from_stage=application.current_stage, to_stage=None,
            action='REJECTED', user=user, comments=comments,
        )
        Task.objects.filter(
            related_type='LOAN_APPLICATION', related_id=application.id,
            status__in=['OPEN', 'IN_PROGRESS'],
        ).update(status='COMPLETED', completed_at=timezone.now())
        return application

    @staticmethod
    @transaction.atomic
    def return_to_applicant(application, user, comments=''):
        if application.status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValueError(f'Cannot return: status is {application.status}.')

        first_stage = WorkflowService.first_stage(application.workflow_template)

        application.status = 'RETURNED'
        application.current_stage = first_stage
        application.save()

        ApplicationTransition.objects.create(
            application=application,
            from_stage=application.current_stage, to_stage=first_stage,
            action='RETURNED', user=user, comments=comments,
        )
        return application

    @staticmethod
    @transaction.atomic
    def withdraw(application, user, comments=''):
        if application.status in ('DISBURSED', 'REJECTED'):
            raise ValueError(f'Cannot withdraw: status is {application.status}.')

        application.status = 'WITHDRAWN'
        application.save()

        ApplicationTransition.objects.create(
            application=application,
            from_stage=application.current_stage, to_stage=None,
            action='WITHDRAWN', user=user, comments=comments,
        )
        return application

    @staticmethod
    @transaction.atomic
    def disburse(application, user, channel='BANK', reference='', disbursement_date=None):
        """
        APPROVED -> DISBURSED.
        Posts GL: DR Loans Receivable / CR Cash|Bank|MoMo
        Updates the linked Loan's status, disbursement fields, and JE link.
        """
        from datetime import date as _date

        if application.status != 'APPROVED':
            raise ValueError(
                f'Cannot disburse: status is {application.status}. '
                f'Application must be APPROVED first.'
            )

        if not application.loan:
            raise ValueError(
                'No Loan record linked to this application. '
                'Approve the application first.'
            )

        loan = application.loan

        if loan.status == 'DISBURSED':
            raise ValueError(f'Loan {loan.loan_number} is already disbursed.')

        when = disbursement_date or _date.today()

        # ---- Resolve GL accounts ----
        from apps.accounting.models import GLAccount
        from apps.accounting.services import AccountingService

        credit_code = {
            'CASH':         '1010',
            'BANK':         '1020',
            'MTN_MOMO':     '1030',
            'AIRTEL_MONEY': '1030',
        }.get(channel, '1020')

        credit_account = GLAccount.objects.filter(
            organization=application.organization,
            code=credit_code,
            is_active=True,
        ).first()
        if not credit_account:
            raise ValueError(
                f'No GL account with code {credit_code} for channel {channel}. '
                f'Configure the chart of accounts first.'
            )

        debit_account = (
            GLAccount.objects.filter(
                organization=application.organization,
                code__startswith='11',
                is_active=True,
            ).first()
            or GLAccount.objects.filter(
                organization=application.organization,
                name__icontains='loans receivable',
                is_active=True,
            ).first()
        )
        if not debit_account:
            raise ValueError(
                'No Loans Receivable GL account found. Create one (e.g., code 1100).'
            )

        amount = application.requested_amount

        # ---- Post the JE ----
        je = AccountingService.create_journal_entry(
            organization=application.organization,
            entry_date=when,
            reference=loan.loan_number,
            description=f'Loan disbursement: {loan.loan_number}',
            lines=[
                {
                    'account_code': debit_account.code,
                    'debit': float(amount),
                    'memo': f'Loan {loan.loan_number} disbursed',
                },
                {
                    'account_code': credit_account.code,
                    'credit': float(amount),
                    'memo': f'Disbursed via {channel}' + (f' - {reference}' if reference else ''),
                },
            ],
            source_type='Loan',
            source_id=loan.id,
            branch=loan.branch,
            user=user,
        )

        # ---- Update the loan ----
        loan.status = 'DISBURSED'
        loan.disbursed_amount = amount
        loan.start_date = when
        loan.disbursement_channel = channel
        loan.disbursement_ref = reference
        loan.disbursement_journal_entry = je
        loan.save(update_fields=[
            'status', 'disbursed_amount', 'start_date',
            'disbursement_channel', 'disbursement_ref',
            'disbursement_journal_entry', 'updated_at',
        ])

        # ---- Update the application ----
        application.status = 'DISBURSED'
        application.save(update_fields=['status', 'updated_at'])

        # ---- MTN DISBURSEMENT INTEGRATION ----
        # Trigger the actual MTN API call to send the money.
        # If this fails, the entire DB transaction (Loan status, JE) is rolled back.
        if channel == 'MTN_MOMO':
            from apps.momo.services import DisbursementService
            try:
                DisbursementService.initiate(
                    org=application.organization,
                    client=application.client,
                    amount=amount,
                    phone=application.client.phone,
                    provider_code='MTN_MOMO',
                    loan=loan,
                    description=f'Loan Disbursement {loan.loan_number}',
                    user=user,
                    branch=application.branch,
                )
            except Exception as e:
                logger.error(f"MTN Disbursement failed for {loan.loan_number}: {e}")
                # Re-raising rolls back the atomic transaction so the loan isn't marked as DISBURSED
                raise ValueError(f"MTN Disbursement failed: {e}")

        # ---- Audit trail ----
        ApplicationTransition.objects.create(
            application=application,
            from_stage=application.current_stage,
            to_stage=None,
            action='DISBURSED',
            user=user,
            comments=f'Disbursed via {channel}. Loan: {loan.loan_number}',
        )

        # ---- Close open tasks ----
        Task.objects.filter(
            related_type='LOAN_APPLICATION',
            related_id=application.id,
            status__in=['OPEN', 'IN_PROGRESS'],
        ).update(status='COMPLETED', completed_at=timezone.now())

        # ─── NOTIFICATION TRIGGER ───────────────────────────────
        # Send disbursement SMS/WhatsApp/Email to the client
        try:
            from apps.notifications.triggers import on_loan_disbursed
            on_loan_disbursed(loan, user=user)
        except Exception:
            pass

        return application


# ============================================================
# Task Service
# ============================================================
class TaskService:

    @staticmethod
    @transaction.atomic
    def complete(task, user, comment=''):
        if task.status in ('COMPLETED', 'CANCELLED'):
            raise ValueError(f'Task already {task.status}.')
        task.status = 'COMPLETED'
        task.completed_at = timezone.now()
        task.save()
        if comment:
            TaskComment.objects.create(task=task, user=user, comment=comment)
        return task

    @staticmethod
    @transaction.atomic
    def reassign(task, new_assignee, user, comment=''):
        old = task.assigned_to
        task.assigned_to = new_assignee
        task.save()
        TaskComment.objects.create(
            task=task, user=user,
            comment=comment or f'Reassigned from {old} to {new_assignee}.',
        )
        return task