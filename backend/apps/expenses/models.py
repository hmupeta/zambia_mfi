from django.db import models
from apps.core.models import Organization, Branch
from apps.payments.models import PAYMENT_METHOD_CHOICES   # <-- reuse, don't redefine
import uuid


# ============================================================
# Shared Choice Constants (expenses-specific only)
# ============================================================
EXPENSE_STATUS_CHOICES = [
    ('DRAFT', 'Draft'),
    ('SUBMITTED', 'Submitted'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('PAID', 'Paid'),
]

EXPENSE_APPROVAL_ACTION_CHOICES = [
    ('SUBMITTED', 'Submitted'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('PAID', 'Paid'),
]

PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Cash'),
    ('MTN_MOMO', 'MTN Mobile Money'),
    ('AIRTEL_MONEY', 'Airtel Money'),
    ('BANK', 'Bank'),
]


# ============================================================
# Expense Category
# ============================================================
class ExpenseCategory(models.Model):
    """
    Categories of operating expenses (rent, salaries, fuel, bank charges).
    Each category points to the GL account to debit when paid.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='expense_categories',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    gl_account = models.ForeignKey(
        'accounting.GLAccount', on_delete=models.PROTECT,
        related_name='expense_categories',
        help_text='GL account to debit when this expense is paid (must be an EXPENSE account)',
    )
    requires_approval = models.BooleanField(
        default=True,
        help_text='If False, expenses in this category auto-approve on submission.',
    )
    approval_threshold = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Amount above which HQ approval is required. Leave blank for default flow.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expense_categories'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_expense_category_code_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# Expense
# ============================================================
class Expense(models.Model):
    """
    A single operating expense. Follows an approval workflow:
        DRAFT -> SUBMITTED -> APPROVED -> PAID
        (or REJECTED at the SUBMITTED stage)
    GL posts when the expense is marked PAID.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='expenses', editable=False,
    )
    expense_number = models.CharField(max_length=40)
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='expenses',
    )
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name='expenses',
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    expense_date = models.DateField()
    payee = models.CharField(max_length=200)
    description = models.TextField()
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH',
    )
    reference = models.CharField(max_length=100, blank=True)
    receipt = models.FileField(
        upload_to='expense_receipts/', null=True, blank=True,
    )

    status = models.CharField(
        max_length=20, choices=EXPENSE_STATUS_CHOICES, default='DRAFT',
    )

    # Workflow timestamps
    submitted_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_expenses',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_expenses',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_expenses',
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    # GL linkage
    journal_entry = models.OneToOneField(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_expense',
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_expenses',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-expense_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'expense_number'],
                name='unique_expense_number_per_org',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'expense_date']),
        ]

    def __str__(self):
        return f"{self.expense_number} - {self.payee} ({self.amount})"

    def save(self, *args, **kwargs):
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)


# ============================================================
# Expense Approval Log
# ============================================================
class ExpenseApproval(models.Model):
    """
    Immutable audit trail of every workflow action on an expense.
    """
    id = models.BigAutoField(primary_key=True)
    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name='approval_log',
    )
    action = models.CharField(max_length=20, choices=EXPENSE_APPROVAL_ACTION_CHOICES)
    user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expense_approvals'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.expense.expense_number} - {self.action} by {self.user}"