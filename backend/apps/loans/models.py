from django.db import models
from apps.core.models import Organization, Branch, User
from apps.core.constants import PAYMENT_METHOD_CHOICES
from apps.clients.models import Client
from datetime import date
import uuid


# ============================================================
# Loans-specific Choice Constants
# ============================================================
# NOTE: PAYMENT_METHOD_CHOICES is imported from apps.core.constants
#       so loans, payments, expenses, and wallets share one enum.

INTEREST_METHOD_CHOICES = [
    ('FLAT', 'Flat'),
    ('REDUCING_BALANCE', 'Reducing Balance'),
    ('DAILY', 'Daily'),
]

REPAYMENT_FREQUENCY_CHOICES = [
    ('DAILY', 'Daily'),
    ('WEEKLY', 'Weekly'),
    ('BIWEEKLY', 'Bi-Weekly'),
    ('MONTHLY', 'Monthly'),
]

LOAN_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('APPROVED', 'Approved'),
    ('DISBURSED', 'Disbursed'),
    ('ACTIVE', 'Active'),
    ('CLOSED', 'Closed'),
    ('DEFAULTED', 'Defaulted'),
]

INSTALLMENT_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('PARTIAL', 'Partial'),
    ('PAID', 'Paid'),
    ('OVERDUE', 'Overdue'),
]

INTEREST_PERIOD_CHOICES = [
    ('ANNUAL', 'Annual'),
    ('MONTHLY', 'Monthly'),
]

CATEGORY_CHOICES = [
    ('AGRICULTURAL', 'Agricultural'),
    ('BUSINESS', 'Business'),
    ('EMERGENCY', 'Emergency'),
    ('SALARY', 'Salary-based'),
    ('GROUP', 'Group loan'),
    ('CONSUMER', 'Consumer'),
    ('OTHER', 'Other'),
]


# ============================================================
# Loan Product
# ============================================================
class LoanProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='loan_products',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    min_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    min_tenure_months = models.IntegerField()
    max_tenure_months = models.IntegerField()

    interest_method = models.CharField(
        max_length=20,
        choices=INTEREST_METHOD_CHOICES,
        default='REDUCING_BALANCE',
    )
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    penalty_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grace_days = models.IntegerField(default=3)

    # ← NEW: Disambiguate whether interest_rate is per-annum or per-month
    interest_rate_period = models.CharField(
        max_length=10,
        choices=INTEREST_PERIOD_CHOICES,
        default='ANNUAL',
        help_text='Whether interest_rate is quoted per-annum or per-month.',
    )

    # ← NEW: Computed on save, BoZ-disclosable annualized EIR
    effective_interest_rate = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text='Computed annualized Effective Interest Rate (%).',
    )

    # ← NEW: Product category for reporting and filtering
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='OTHER',
    )

    # ← NEW: Days between disbursement and the first installment due date
    first_installment_grace_days = models.IntegerField(
        default=0,
        help_text='Days between disbursement and first installment due date.',
    )

    repayment_frequency = models.CharField(
        max_length=20,
        choices=REPAYMENT_FREQUENCY_CHOICES,
        default='WEEKLY',
    )

    requires_guarantor = models.BooleanField(default=False)
    requires_collateral = models.BooleanField(default=False)
    allow_group_loan = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loan_products'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_loan_product_code_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    # ← NEW: Compute EIR on save. Lazy import + swallow errors so that
    # missing services_pricing module never breaks a save.
    def save(self, *args, **kwargs):
        try:
            from .services_pricing import compute_eir
            self.effective_interest_rate = compute_eir(self)
        except Exception:
            pass
        super().save(*args, **kwargs)


# ============================================================
# Branch Loan Product
# ============================================================
class BranchLoanProduct(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'branch_loan_products'
        unique_together = ['branch', 'loan_product']

    def __str__(self):
        return f"{self.branch.code} - {self.loan_product.code}"


# ============================================================
# Loan Product Fee  ← NEW MODEL
# ============================================================
class LoanProductFee(models.Model):
    FEE_TYPE_CHOICES = [
        ('APPLICATION', 'Application fee'),
        ('PROCESSING', 'Processing fee'),
        ('INSURANCE', 'Insurance'),
        ('MONITORING', 'Monitoring fee'),
        ('OTHER', 'Other'),
    ]
    CALC_METHOD_CHOICES = [
        ('FLAT', 'Flat amount'),
        ('PCT_PRINCIPAL', '% of principal'),
        ('PCT_OUTSTANDING', '% of outstanding balance'),
    ]
    CHARGE_TIMING_CHOICES = [
        ('DEDUCT_DISBURSEMENT', 'Deducted from disbursement'),
        ('ADD_FIRST_INSTALLMENT', 'Added to first installment'),
        ('SEPARATE', 'Charged separately'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.CASCADE, related_name='fees',
    )
    fee_type = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    calculation_method = models.CharField(
        max_length=20, choices=CALC_METHOD_CHOICES, default='FLAT',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    charge_timing = models.CharField(
        max_length=30, choices=CHARGE_TIMING_CHOICES,
        default='DEDUCT_DISBURSEMENT',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loan_product_fees'
        ordering = ['fee_type', 'name']

    def __str__(self):
        return f'{self.loan_product.code} — {self.name}'

    def compute(self, principal, outstanding=None):
        """Return the fee amount given principal and (optionally) outstanding."""
        from decimal import Decimal, ROUND_HALF_UP
        principal = Decimal(str(principal or 0))
        if self.calculation_method == 'FLAT':
            return Decimal(str(self.amount or 0))
        if self.calculation_method == 'PCT_PRINCIPAL':
            return (
                principal * Decimal(str(self.percentage or 0)) / Decimal('100')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if self.calculation_method == 'PCT_OUTSTANDING' and outstanding is not None:
            return (
                Decimal(str(outstanding)) * Decimal(str(self.percentage or 0))
                / Decimal('100')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0')


# ============================================================
# Loan Group
# ============================================================
class LoanGroup(models.Model):
    GROUP_STATUS_CHOICES = [
        ('FORMING', 'Forming'),
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('CLOSED', 'Closed'),
    ]

    MEETING_FREQ_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('BIWEEKLY', 'Bi-Weekly'),
        ('MONTHLY', 'Monthly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='loan_groups', editable=False,
    )
    group_name = models.CharField(max_length=100)
    group_code = models.CharField(max_length=30, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    leader = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True,
        related_name='led_groups',
    )

    status = models.CharField(
        max_length=20, choices=GROUP_STATUS_CHOICES, default='FORMING',
    )

    # Cycle (VLSA-style: 9-12 month rounds)
    cycle_number = models.PositiveIntegerField(default=1)
    cycle_start_date = models.DateField(null=True, blank=True)
    cycle_end_date = models.DateField(null=True, blank=True)

    # Meetings
    meeting_frequency = models.CharField(
        max_length=20, choices=MEETING_FREQ_CHOICES, default='WEEKLY',
    )
    meeting_day = models.CharField(max_length=10, blank=True)  # 'Monday'
    meeting_location = models.CharField(max_length=200, blank=True)

    # Savings pool (can offset defaults)
    savings_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Cross-guarantee configuration
    requires_cross_guarantee = models.BooleanField(default=True)
    min_members = models.PositiveIntegerField(default=5)
    max_members = models.PositiveIntegerField(default=30)

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_groups',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loan_groups'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'group_code'],
                name='unique_group_code_per_org',
                condition=models.Q(group_code__gt=''),
            ),
        ]

    def __str__(self):
        return self.group_name

    def save(self, *args, **kwargs):
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)

    @property
    def active_members(self):
        return self.members.filter(is_active=True)

    @property
    def member_count(self):
        return self.active_members.count()


class LoanGroupMember(models.Model):
    MEMBER_ROLE_CHOICES = [
        ('LEADER', 'Group Leader'),
        ('TREASURER', 'Treasurer'),
        ('SECRETARY', 'Secretary'),
        ('MEMBER', 'Member'),
    ]

    loan_group = models.ForeignKey(
        LoanGroup, on_delete=models.CASCADE, related_name='members',
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE)

    role = models.CharField(max_length=20, choices=MEMBER_ROLE_CHOICES, default='MEMBER')
    is_leader = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    joined_at = models.DateField(default=date.today)
    exited_at = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=200, blank=True)

    savings_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shares = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'loan_group_members'
        unique_together = ['loan_group', 'client']

    def __str__(self):
        return f"{self.loan_group.group_name} - {self.client}"


# ============================================================
# Loan
# ============================================================
class Loan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='loans', editable=False,
    )
    loan_number = models.CharField(max_length=30)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='loans')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='loans')
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT)
    loan_officer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='managed_loans',
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='approved_loans',
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_interest = models.DecimalField(max_digits=12, decimal_places=2)
    total_penalties = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2)

    start_date = models.DateField()
    maturity_date = models.DateField()

    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    interest_method = models.CharField(
        max_length=20, choices=INTEREST_METHOD_CHOICES,
    )
    repayment_frequency = models.CharField(
        max_length=20, choices=REPAYMENT_FREQUENCY_CHOICES,
    )

    status = models.CharField(
        max_length=20, choices=LOAN_STATUS_CHOICES, default='PENDING',
    )

    # Uses PAYMENT_METHOD_CHOICES from apps.core.constants (shared enum)
    disbursement_channel = models.CharField(
        max_length=20,
        blank=True,
        choices=PAYMENT_METHOD_CHOICES,
    )
    disbursement_ref = models.CharField(max_length=100, blank=True)

    loan_group = models.ForeignKey(
        LoanGroup, on_delete=models.SET_NULL, null=True, blank=True,
    )
    is_fully_repaid = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Link to the GL journal entry generated on disbursement
    disbursement_journal_entry = models.OneToOneField(
        'accounting.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='source_loan_disbursement',
        help_text='GL journal entry for the disbursement',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loans'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'loan_number'],
                name='unique_loan_number_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.loan_number} - {self.client}"

    def save(self, *args, **kwargs):
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)


# ============================================================
# Loan Installment
# ============================================================
class LoanInstallment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='installments')
    installment_no = models.IntegerField()
    due_date = models.DateField()

    principal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2)
    penalty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=INSTALLMENT_STATUS_CHOICES, default='PENDING',
    )
    # NEW: Track when penalty was last applied to avoid double-charging
    last_penalty_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'loan_installments'
        unique_together = ['loan', 'installment_no']
        ordering = ['installment_no']

    def __str__(self):
        return f"{self.loan.loan_number} - installment {self.installment_no}"


# ============================================================
# Group Meeting (Phase AC)
# ============================================================
class GroupMeeting(models.Model):
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('HELD', 'Held'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan_group = models.ForeignKey(
        LoanGroup, on_delete=models.CASCADE, related_name='meetings',
    )
    meeting_number = models.PositiveIntegerField()
    scheduled_date = models.DateField()
    actual_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    agenda = models.TextField(blank=True)
    minutes = models.TextField(blank=True)

    attendance_count = models.PositiveIntegerField(default=0)
    savings_collected = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    collections_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_meetings'
        ordering = ['-scheduled_date']
        unique_together = ['loan_group', 'meeting_number']

    def __str__(self):
        return f"{self.loan_group.group_name} - Meeting {self.meeting_number}"


class GroupAttendance(models.Model):
    id = models.BigAutoField(primary_key=True)
    meeting = models.ForeignKey(
        GroupMeeting, on_delete=models.CASCADE, related_name='attendances',
    )
    member = models.ForeignKey(LoanGroupMember, on_delete=models.CASCADE)
    is_present = models.BooleanField(default=False)
    is_excused = models.BooleanField(default=False)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'group_attendances'
        unique_together = ['meeting', 'member']


# ============================================================
# Group Collection (one receipt → N loan payments)
# ============================================================
class GroupCollection(models.Model):
    CHANNEL_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK', 'Bank'),
        ('MTN_MOMO', 'MTN Mobile Money'),
        ('AIRTEL_MONEY', 'Airtel Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='group_collections', editable=False,
    )
    loan_group = models.ForeignKey(
        LoanGroup, on_delete=models.PROTECT, related_name='collections',
    )
    meeting = models.ForeignKey(
        GroupMeeting, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='collections',
    )
    collection_number = models.CharField(max_length=40, unique=True, db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='CASH')
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    member_count = models.PositiveIntegerField(default=0)
    journal_entry = models.ForeignKey(
        'accounting.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='group_collections',
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_collections'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.collection_number} - {self.loan_group.group_name}"

    def save(self, *args, **kwargs):
        if self.loan_group_id and not self.organization_id:
            self.organization_id = self.loan_group.organization_id
        super().save(*args, **kwargs)

class PromiseToPay(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('KEPT', 'Kept'),
        ('BROKEN', 'Broken'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='promises')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    promised_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)
    
    logged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='logged_promises')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loan_promises_to_pay'
        ordering = ['promised_date', '-created_at']

    def __str__(self):
        return f"{self.loan.loan_number} - K{self.amount} on {self.promised_date}"


class SavingsTransaction(models.Model):
    TXN_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='savings_transactions')
    loan_group = models.ForeignKey('LoanGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name='savings_transactions')
    
    transaction_type = models.CharField(max_length=20, choices=TXN_TYPE_CHOICES, default='DEPOSIT')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'savings_transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client} - {self.transaction_type} {self.amount}"