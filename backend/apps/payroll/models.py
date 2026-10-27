# apps/payroll/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
import uuid


class StaffProfile(models.Model):
    """Extends the core User model with HR and payroll-specific data."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payroll_profile')
    
    # Financial Details
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0)]
    )
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    
    # Statutory Numbers (Zambia)
    napsa_number = models.CharField(max_length=20, blank=True, verbose_name="NAPSA Number")
    nhima_number = models.CharField(max_length=20, blank=True, verbose_name="NHIMA Number")
    tin_number = models.CharField(max_length=20, blank=True, verbose_name="TPIN")

    def __str__(self):
        return f"{self.user.username} - K{self.base_salary}"


class CommissionRule(models.Model):
    """Defines how commissions are calculated for different roles."""
    ROLE_CHOICES = (
        ('LOAN_OFFICER', 'Loan Officer'),
        ('BRANCH_MANAGER', 'Branch Manager'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('core.Organization', on_delete=models.CASCADE, related_name='commission_rules')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    # Rules (Percentage)
    percentage_of_disbursed = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, 
        help_text="Percentage of total loan volume disbursed (e.g., 1.5 for 1.5%)"
    )
    percentage_of_collections = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, 
        help_text="Percentage of total repayments collected (e.g., 2.0 for 2%)"
    )
    
    class Meta:
        unique_together = ('organization', 'role')

    def __str__(self):
        return f"{self.organization.code} - {self.get_role_display()} Commission"


class PayrollPeriod(models.Model):
    """Defines the cutoff dates for a specific payroll month."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('core.Organization', on_delete=models.CASCADE, related_name='payroll_periods')
    name = models.CharField(max_length=50, help_text="e.g., October 2026")
    
    start_date = models.DateField(help_text="Start of the working period (e.g., 26th of prev month)")
    end_date = models.DateField(help_text="End of the working period (e.g., 25th of current month)")
    payment_date = models.DateField(help_text="Date salaries are paid to the bank")
    is_closed = models.BooleanField(default=False, help_text="Locked periods cannot be processed again")

    class Meta:
        unique_together = ('organization', 'start_date', 'end_date')
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"


class PayrollSetting(models.Model):
    """Maps payroll components to the Chart of Accounts for GL posting."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField('core.Organization', on_delete=models.CASCADE, related_name='payroll_settings')
    
    # Expense Accounts (Debits)
    salary_expense_account = models.ForeignKey('accounting.GLAccount', on_delete=models.PROTECT, related_name='payroll_salary_expense')
    
    # Liability Accounts (Credits)
    paye_payable_account = models.ForeignKey('accounting.GLAccount', on_delete=models.PROTECT, related_name='payroll_paye_payable')
    napsa_payable_account = models.ForeignKey('accounting.GLAccount', on_delete=models.PROTECT, related_name='payroll_napsa_payable')
    nhima_payable_account = models.ForeignKey('accounting.GLAccount', on_delete=models.PROTECT, related_name='payroll_nhima_payable')
    
    # Bank Account (Credit)
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, related_name='payroll_bank')

    def __str__(self):
        return f"Payroll Settings - {self.organization.name}"


class PayrollRun(models.Model):
    """A monthly payroll batch."""
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('core.Organization', on_delete=models.CASCADE, related_name='payroll_runs')
    
    # REPLACED 'month' with 'period'
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name='runs')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ('organization', 'period') # Changed from 'month'
        ordering = ['-period__start_date']

    def __str__(self):
        return f"{self.organization.code} - {self.period.name}"


class Payslip(models.Model):
    """Individual payslip for a staff member for a specific month."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payslips')
    
    # Earnings
    basic_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    commission_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Deductions
    napsa_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    nhima_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paye_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Totals
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('payroll_run', 'staff')
        ordering = ['staff__first_name']

    def __str__(self):
        return f"Payslip {self.staff.username} - {self.payroll_run.period.name}"