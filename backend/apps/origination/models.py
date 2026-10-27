from django.db import models
from apps.core.models import Organization, Branch
from apps.clients.models import Client
from apps.loans.models import Loan, LoanProduct
import uuid


# ============================================================
# Choice constants
# ============================================================
APPLICATION_STATUS_CHOICES = [
    ('DRAFT', 'Draft'),
    ('SUBMITTED', 'Submitted'),
    ('UNDER_REVIEW', 'Under Review'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('RETURNED', 'Returned for Revision'),
    ('WITHDRAWN', 'Withdrawn'),
    ('DISBURSED', 'Disbursed'),
]

APPLICATION_ACTION_CHOICES = [
    ('SUBMITTED', 'Submitted'),
    ('MOVED', 'Moved to Next Stage'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('RETURNED', 'Returned'),
    ('WITHDRAWN', 'Withdrawn'),
    ('DISBURSED', 'Disbursed'),
]

REVIEW_RECOMMENDATION_CHOICES = [
    ('APPROVE', 'Approve'),
    ('REJECT', 'Reject'),
    ('RETURN', 'Return for Revision'),
    ('FLAG', 'Flag for Attention'),
]

PURPOSE_CHOICES = [
    ('BUSINESS_CAPITAL', 'Business Capital'),
    ('EQUIPMENT', 'Equipment Purchase'),
    ('INVENTORY', 'Inventory / Stock'),
    ('AGRICULTURE', 'Agriculture / Farming'),
    ('EDUCATION', 'Education'),
    ('MEDICAL', 'Medical'),
    ('EMERGENCY', 'Emergency'),
    ('OTHER', 'Other'),
]

CREDIT_SCORE_GRADE_CHOICES = [
    ('A', 'A — Excellent'),
    ('B', 'B — Good'),
    ('C', 'C — Fair'),
    ('D', 'D — High Risk'),
]

TASK_STATUS_CHOICES = [
    ('OPEN', 'Open'),
    ('IN_PROGRESS', 'In Progress'),
    ('COMPLETED', 'Completed'),
    ('CANCELLED', 'Cancelled'),
]

TASK_PRIORITY_CHOICES = [
    ('LOW', 'Low'),
    ('NORMAL', 'Normal'),
    ('HIGH', 'High'),
    ('URGENT', 'Urgent'),
]

TASK_RELATED_TYPE_CHOICES = [
    ('LOAN_APPLICATION', 'Loan Application'),
    ('LOAN', 'Loan'),
    ('CLIENT', 'Client'),
    ('PAYMENT', 'Payment'),
    ('OTHER', 'Other'),
]


# ============================================================
# Workflow Template — the pipeline definition
# ============================================================
class WorkflowTemplate(models.Model):
    """
    A named approval pipeline. Assigned to a loan product (or product-range)
    and determines the ordered stages an application goes through.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='workflow_templates',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.CASCADE, null=True, blank=True,
        related_name='workflow_templates',
        help_text='Leave blank to apply to all products.',
    )
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False, help_text='Fallback workflow if no specific match found.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workflow_templates'
        ordering = ['organization', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'],
                name='unique_workflow_template_name_per_org',
            ),
        ]

    def __str__(self):
        return self.name


class WorkflowStage(models.Model):
    """
    One ordered step within a workflow. The loan officer moves the application
    through these until it reaches a terminal (approve/reject/disburse).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        WorkflowTemplate, on_delete=models.CASCADE, related_name='stages',
    )
    order = models.PositiveIntegerField()
    name = models.CharField(max_length=100)
    role_required = models.CharField(
        max_length=20,
        choices=[
            ('HQ_ADMIN', 'HQ Admin'),
            ('BRANCH_MANAGER', 'Branch Manager'),
            ('LOAN_OFFICER', 'Loan Officer'),
        ],
    )
    sla_hours = models.PositiveIntegerField(
        default=24, help_text='Target hours to complete this stage.',
    )
    can_reject = models.BooleanField(default=True)
    is_final = models.BooleanField(
        default=False,
        help_text='If True, completion of this stage approves the application.',
    )

    class Meta:
        db_table = 'workflow_stages'
        ordering = ['template', 'order']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'order'],
                name='unique_workflow_stage_order_per_template',
            ),
        ]

    def __str__(self):
        return f'{self.template.name} · {self.order}. {self.name}'


# ============================================================
# Loan Application
# ============================================================
class LoanApplication(models.Model):
    """
    A client's request for credit. Goes through the workflow template,
    ends in APPROVED (which creates a Loan) or REJECTED.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='loan_applications', editable=False,
    )
    application_number = models.CharField(max_length=40)
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='loan_applications',
    )
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='loan_applications',
    )
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.PROTECT, related_name='loan_applications',
    )
    loan_officer = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_applications',
    )

    # ---- Requested terms ----
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2)
    requested_tenure_months = models.PositiveIntegerField()
    requested_repayment_frequency = models.CharField(max_length=20)
    purpose = models.CharField(
        max_length=30, choices=PURPOSE_CHOICES, default='BUSINESS_CAPITAL',
    )
    purpose_notes = models.TextField(blank=True)

    # ---- Appraisal data ----
    monthly_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monthly_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    existing_debts = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_worth = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    collateral_summary = models.TextField(blank=True)
    appraisal_notes = models.TextField(blank=True)

    credit_score = models.IntegerField(null=True, blank=True)
    credit_score_grade = models.CharField(
        max_length=1, choices=CREDIT_SCORE_GRADE_CHOICES, blank=True,
    )

    # ---- Workflow state ----
    workflow_template = models.ForeignKey(
        WorkflowTemplate, on_delete=models.PROTECT, null=True, blank=True,
        related_name='applications',
    )
    current_stage = models.ForeignKey(
        WorkflowStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='applications_here',
    )
    status = models.CharField(
        max_length=20, choices=APPLICATION_STATUS_CHOICES, default='DRAFT',
    )

    # ---- Workflow timestamps ----
    submitted_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_applications',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='decided_applications',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)

    # ---- Output link ----
    loan = models.OneToOneField(
        Loan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='source_application',
        help_text='The Loan record created on approval.',
    )

    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_applications',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loan_applications'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'application_number'],
                name='unique_application_number_per_org',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['branch', 'status']),
        ]

    def __str__(self):
        return f'{self.application_number} · {self.client}'

    def save(self, *args, **kwargs):
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)


# ============================================================
# Application Documents
# ============================================================
class ApplicationDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name='documents',
    )
    document_type = models.CharField(
        max_length=30,
        choices=[
            ('NRC', 'National Registration Card'),
            ('PHOTO', 'Borrower Photo'), 
            ('PAYSLIP', 'Payslip / Income Proof'),
            ('BANK_STATEMENT', 'Bank Statement'),
            ('COLLATERAL', 'Collateral Evidence'),
            ('GUARANTEE_LETTER', 'Guarantee Letter'),
            ('BUSINESS_LICENSE', 'Business License'),
            ('OTHER', 'Other'),
        ],
    )
    file = models.FileField(upload_to='applications/documents/')
    notes = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'application_documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.application.application_number} · {self.document_type}'


# ============================================================
# Application Transition — immutable audit log
# ============================================================
class ApplicationTransition(models.Model):
    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name='transitions',
    )
    from_stage = models.ForeignKey(
        WorkflowStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transitions_from',
    )
    to_stage = models.ForeignKey(
        WorkflowStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transitions_to',
    )
    action = models.CharField(max_length=20, choices=APPLICATION_ACTION_CHOICES)
    user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'application_transitions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.application.application_number} · {self.action}'


# ============================================================
# Application Review — reviewer notes on a specific stage
# ============================================================
class ApplicationReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name='reviews',
    )
    stage = models.ForeignKey(
        WorkflowStage, on_delete=models.SET_NULL, null=True, blank=True,
    )
    reviewer = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='application_reviews',
    )
    recommendation = models.CharField(
        max_length=10, choices=REVIEW_RECOMMENDATION_CHOICES,
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'application_reviews'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.application.application_number} · {self.recommendation}'


# ============================================================
# Task Management
# ============================================================
class Task(models.Model):
    """
    A follow-up task assigned to a user. Polymorphic — can link to any entity.
    Used for approval queues, follow-ups, client visits, call-backs, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='tasks', editable=False,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    assigned_to = models.ForeignKey(
        'core.User', on_delete=models.CASCADE, related_name='assigned_tasks',
    )
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tasks',
    )

    # ---- Polymorphic link ----
    related_type = models.CharField(
        max_length=30, choices=TASK_RELATED_TYPE_CHOICES, blank=True,
    )
    related_id = models.UUIDField(null=True, blank=True)

    # ---- Lifecycle ----
    priority = models.CharField(
        max_length=10, choices=TASK_PRIORITY_CHOICES, default='NORMAL',
    )
    status = models.CharField(
        max_length=20, choices=TASK_STATUS_CHOICES, default='OPEN',
    )
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tasks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['related_type', 'related_id']),
        ]

    def __str__(self):
        return f'{self.title} → {self.assigned_to}'


class TaskComment(models.Model):
    id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_comments'
        ordering = ['created_at']

    def __str__(self):
        return f'Comment on {self.task_id} by {self.user}'

# ... existing imports ...

# Add this at the bottom of origination/models.py

class Guarantor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name='guarantors',
        help_text='The loan application this guarantor is attached to.'
    )
    
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    nrc = models.CharField(max_length=30, verbose_name="National ID / NRC")
    relationship = models.CharField(max_length=100, help_text="e.g. Spouse, Business Partner")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'application_guarantors'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.full_name} - {self.application.application_number}'