from django.db import models
from apps.core.models import Organization, Branch
from apps.loans.models import Loan
import uuid


# ============================================================
# Choice constants
# ============================================================
RESTRUCTURE_TYPE_CHOICES = [
    ('EXTEND_TERM', 'Extend Term'),
    ('REDUCE_AMOUNT', 'Reduce Installment Amount'),
    ('MORATORIUM', 'Moratorium (Payment Holiday)'),
    ('REFINANCE', 'Refinance'),
]

RESTRUCTURE_STATUS_CHOICES = [
    ('PROPOSED', 'Proposed'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('APPLIED', 'Applied'),
    ('CANCELLED', 'Cancelled'),
]

RESTRUCTURE_REASON_CHOICES = [
    ('FINANCIAL_HARDSHIP', 'Financial Hardship'),
    ('MEDICAL', 'Medical Emergency'),
    ('NATURAL_DISASTER', 'Natural Disaster'),
    ('BUSINESS_DOWNTURN', 'Business Downturn'),
    ('SEASONAL', 'Seasonal (e.g., Farming)'),
    ('OTHER', 'Other'),
]

# NOTE: RESTRUCTURE_EVENT_ACTION_CHOICES has been removed.
#       RestructureEvent.action now reuses RESTRUCTURE_STATUS_CHOICES —
#       same values, single source of truth.


# ============================================================
# Loan Restructure
# ============================================================
class LoanRestructure(models.Model):
    """
    A proposal to change the repayment schedule of an existing loan.
    Requires approval, then application (which regenerates installments).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='loan_restructures', editable=False,
    )
    loan = models.ForeignKey(
        Loan, on_delete=models.PROTECT, related_name='restructures',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='loan_restructures',
    )

    restructure_type = models.CharField(
        max_length=20, choices=RESTRUCTURE_TYPE_CHOICES,
    )
    reason = models.CharField(
        max_length=30, choices=RESTRUCTURE_REASON_CHOICES,
    )
    reason_notes = models.TextField(blank=True)

    original_principal = models.DecimalField(max_digits=15, decimal_places=2)
    original_balance = models.DecimalField(max_digits=15, decimal_places=2)
    original_installment_count = models.IntegerField()
    original_maturity_date = models.DateField()

    new_start_date = models.DateField()
    new_maturity_date = models.DateField()
    new_installment_count = models.IntegerField()
    new_installment_amount = models.DecimalField(max_digits=15, decimal_places=2)
    new_interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Set equal to original if interest is not changing.',
    )
    new_repayment_frequency = models.CharField(max_length=20)

    waive_penalties = models.BooleanField(
        default=False,
        help_text='Waive all accrued penalties as part of this restructure.',
    )
    penalties_waived_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
    )
    moratorium_days = models.IntegerField(
        default=0,
        help_text='Days of payment holiday at the start of the new schedule.',
    )

    status = models.CharField(
        max_length=20, choices=RESTRUCTURE_STATUS_CHOICES, default='PROPOSED',
    )
    proposed_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='proposed_restructures',
    )
    proposed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_restructures',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rejected_restructures',
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    journal_entry = models.OneToOneField(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_restructure',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loan_restructures'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['loan', 'status']),
        ]

    def __str__(self):
        return f"RESTR-{self.loan.loan_number} ({self.get_restructure_type_display()})"

    def save(self, *args, **kwargs):
        if self.loan_id and not self.organization_id:
            self.organization_id = self.loan.organization_id
        if self.loan_id and not self.branch_id:
            self.branch_id = self.loan.branch_id
        super().save(*args, **kwargs)


# ============================================================
# Restructure Audit Log
# ============================================================
class RestructureEvent(models.Model):
    """
    Immutable trail of every workflow action on a restructure.
    Uses RESTRUCTURE_STATUS_CHOICES so it shares one enum with
    LoanRestructure.status.
    """
    id = models.BigAutoField(primary_key=True)
    restructure = models.ForeignKey(
        LoanRestructure, on_delete=models.CASCADE, related_name='events',
    )
    action = models.CharField(
        max_length=20,
        choices=RESTRUCTURE_STATUS_CHOICES,   # <-- shared constant
    )
    user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'restructure_events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.restructure_id} - {self.action}"