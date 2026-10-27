from django.db import models
from apps.core.models import Organization, Branch
import uuid


# ============================================================
# Chart of Accounts
# ============================================================
class GLAccount(models.Model):
    """
    General Ledger Account — one per organization (tenant).
    Codes follow the ZICA-recommended 5-tier scheme:
        1xxx = Assets, 2xxx = Liabilities, 3xxx = Equity,
        4xxx = Income, 5xxx = Expenses
    """
    ACCOUNT_TYPE_CHOICES = [
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'),
        ('EQUITY', 'Equity'),
        ('INCOME', 'Income'),
        ('EXPENSE', 'Expense'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='gl_accounts',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children',
    )
    is_contra = models.BooleanField(
        default=False,
        help_text="Contra-account (e.g., Accumulated Depreciation, Allowance for Loan Losses)",
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gl_accounts'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_gl_code_per_org',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'account_type']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_debit_normal(self):
        """Assets and Expenses are debit-normal; Liabilities, Equity, Income are credit-normal."""
        return self.account_type in ('ASSET', 'EXPENSE')


# ============================================================
# Journal Entry (the balanced header)
# ============================================================
class JournalEntry(models.Model):
    """
    A balanced journal entry — one per financial event.
    Total debits MUST equal total credits across its JournalLines.
    """
    SOURCE_TYPE_CHOICES = [
        ('Loan', 'Loan'),
        ('Payment', 'Payment'),
        ('InterestAccrual', 'Interest Accrual'),
        ('PenaltyAccrual', 'Penalty Accrual'),
        ('Provision', 'Loan Loss Provision'),
        ('WriteOff', 'Write-Off'),
        ('Restructure', 'Restructure'),
        ('WalletTransfer', 'Wallet Transfer'),
        ('Expense', 'Operating Expense'),
        ('Manual', 'Manual Journal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='journal_entries',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='journal_entries',
    )

    entry_date = models.DateField()
    reference = models.CharField(max_length=100)
    description = models.TextField()

    source_type = models.CharField(
        max_length=50, choices=SOURCE_TYPE_CHOICES, blank=True,
    )
    source_id = models.UUIDField(null=True, blank=True)

    is_posted = models.BooleanField(default=False)
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.OneToOneField(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reverses',
    )

    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'journal_entries'
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'entry_date']),
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return f"JE-{self.reference} ({self.entry_date})"

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), start=0)

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), start=0)

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit


# ============================================================
# Journal Line (debit/credit leg)
# ============================================================
class JournalLine(models.Model):
    id = models.BigAutoField(primary_key=True)
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name='lines',
    )
    account = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name='journal_lines',
    )
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    memo = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'journal_lines'
        indexes = [
            models.Index(fields=['account', 'journal_entry']),
        ]

    def __str__(self):
        return f"{self.account.code}: DR {self.debit} CR {self.credit}"


# ============================================================
# Bank Reconciliation
# ============================================================
class BankAccount(models.Model):
    """
    A real bank account held by a branch.
    Points to the GL account that mirrors it (usually 1020 Bank).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='bank_accounts',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='bank_accounts',
    )
    gl_account = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name='bank_accounts',
        help_text='GL account this bank account feeds (e.g., 1020)',
    )
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    currency = models.CharField(max_length=3, default='ZMW')
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bank_accounts'
        ordering = ['bank_name', 'account_number']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'account_number'],
                name='unique_bank_account_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class BankStatement(models.Model):
    """
    A statement uploaded or entered for a period.
    Reconciliation is done at the statement level.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('IN_PROGRESS', 'In Progress'),
        ('RECONCILED', 'Reconciled'),
    ]
    SOURCE_CHOICES = [
        ('MANUAL', 'Manual Entry'),
        ('CSV', 'CSV Import'),
        ('PDF', 'PDF Import'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='bank_statements',
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='statements',
    )
    period_from = models.DateField()
    period_to = models.DateField()
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='MANUAL')
    statement_file = models.FileField(
        upload_to='bank_statements/', null=True, blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_statements'
        ordering = ['-period_to', '-created_at']

    def __str__(self):
        return f"{self.bank_account.account_number} - {self.period_from} to {self.period_to}"

    def save(self, *args, **kwargs):
        if self.bank_account_id and not self.organization_id:
            self.organization_id = self.bank_account.organization_id
        super().save(*args, **kwargs)


class BankStatementLine(models.Model):
    """
    One transaction on the bank statement.
    Can be matched to a single GL journal line.
    """
    MATCH_STATUS_CHOICES = [
        ('UNMATCHED', 'Unmatched'),
        ('AUTO_MATCHED', 'Auto-matched'),
        ('MANUAL_MATCHED', 'Manually matched'),
        ('EXCLUDED', 'Excluded'),
    ]

    id = models.BigAutoField(primary_key=True)
    statement = models.ForeignKey(
        BankStatement, on_delete=models.CASCADE, related_name='lines',
    )
    transaction_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True)

    # Bank statement convention:
    #   debit  = money OUT of the bank account (a payment made)
    #   credit = money INTO the bank account (a deposit/collection)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Running balance on the statement, if provided',
    )

    # NOTE (Phase II refactor): Currently 1:1. Mobile money aggregator deposits
    # (e.g., a single K50,000 MTN settlement covering 50 loan repayments) will
    # require migration to a ReconciliationMatch through-model. Defer until
    # MoMo aggregator onboarding.
    matched_journal_line = models.OneToOneField(
        JournalLine, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='statement_match',
    )
    match_status = models.CharField(
        max_length=20, choices=MATCH_STATUS_CHOICES, default='UNMATCHED',
    )
    match_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Fuzzy match confidence score 0–100 (from auto-match engine)',
    )
    match_rule = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. "auto-ref+amount", "manual", "fuzzy-desc"',
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    matched_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bank_line_matches',
    )

    class Meta:
        db_table = 'bank_statement_lines'
        ordering = ['transaction_date', 'id']
        indexes = [
            models.Index(fields=['statement', 'match_status']),
            models.Index(fields=['matched_journal_line']),
        ]

    def __str__(self):
        return f"{self.transaction_date} - {self.description}"


class BankReconciliation(models.Model):
    """
    A reconciliation session snapshot — matches statement to GL.
    Generated for a bank statement, holds the computed numbers.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('COMPLETED', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='bank_reconciliations',
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='reconciliations',
    )
    statement = models.ForeignKey(
        BankStatement, on_delete=models.CASCADE, related_name='reconciliations',
    )
    as_of_date = models.DateField()

    # From statement
    statement_opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statement_closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # From GL
    gl_opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    gl_closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Computed reconciliation
    reconciled_difference = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_reconciled = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_reconciliations',
    )
    completed_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_reconciliations',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bank_reconciliations'
        ordering = ['-as_of_date']

    def __str__(self):
        return f"Reconciliation {self.bank_account.account_number} @ {self.as_of_date}"


# ============================================================
# Loan Loss Provision Register
# ============================================================
class LoanLossProvision(models.Model):
    """
    BoZ Microfinance Classification and Provisioning Directive (2018).
    Records the provisioning status of each loan on a given date.
    """
    CLASSIFICATION_CHOICES = [
        ('PERFORMING', 'Performing'),
        ('WATCH', 'Watch'),
        ('SUBSTANDARD', 'Substandard'),
        ('DOUBTFUL', 'Doubtful'),
        ('LOSS', 'Loss'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.CASCADE, related_name='provisions',
    )
    provision_date = models.DateField()
    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES)
    days_past_due = models.IntegerField(default=0)
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    provision_rate = models.DecimalField(max_digits=5, decimal_places=4)
    provision_amount = models.DecimalField(max_digits=15, decimal_places=2)
    prior_provision = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    provision_movement = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='provision_record',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loan_loss_provisions'
        ordering = ['-provision_date', 'loan__loan_number']
        constraints = [
            models.UniqueConstraint(
                fields=['loan', 'provision_date'],
                name='unique_loan_provision_per_date',
            ),
        ]

    def __str__(self):
        return f"{self.loan.loan_number} @ {self.provision_date}: {self.classification} ({self.provision_amount})"