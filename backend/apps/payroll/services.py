# apps/payroll/services.py
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.db import transaction
from django.http import HttpResponse
from datetime import timedelta
import csv

from apps.payments.models import Payment
from apps.loans.models import Loan
from apps.accounting.models import JournalEntry, JournalLine
from .models import PayrollRun, Payslip, CommissionRule, PayrollSetting

class PayrollService:
    
    @staticmethod
    def calculate_statutory_deductions(gross_pay):
        """
        Calculates Zambian statutory deductions: NAPSA, NHIMA, and PAYE.
        (Note: PAYE brackets should be updated annually based on ZRA guidelines).
        """
        # 1. NAPSA (5% capped at K1,200)
        napsa = min(gross_pay * Decimal('0.05'), Decimal('1200.00'))
        
        # 2. NHIMA (1% of gross)
        nhima = gross_pay * Decimal('0.01')
        
        # 3. PAYE (Simplified Progressive Brackets based on taxable income)
        taxable_income = gross_pay - napsa - nhima
        paye = Decimal('0.00')
        
        if taxable_income > Decimal('5100'):
            # 0 - 5,100 = 0%
            # 5,100 - 7,100 = 20%
            # 7,100 - 37,100 = 30%
            # 37,100+ = 37%
            
            band1 = min(taxable_income, Decimal('7100')) - Decimal('5100')
            paye += band1 * Decimal('0.20')
            
            if taxable_income > Decimal('7100'):
                band2 = min(taxable_income, Decimal('37100')) - Decimal('7100')
                paye += band2 * Decimal('0.30')
                
            if taxable_income > Decimal('37100'):
                band3 = taxable_income - Decimal('37100')
                paye += band3 * Decimal('0.37')

        return napsa.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), \
               nhima.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), \
               paye.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    @transaction.atomic
    def generate_payslips(payroll_run: PayrollRun, user):
        """
        Calculates payslips for all active staff, posts to General Ledger,
        and locks the PayrollPeriod.
        """
        org = payroll_run.organization
        period = payroll_run.period
        
        # Use the exact dates from the PayrollPeriod
        start_date = period.start_date
        end_date = period.end_date

        # Get all active staff
        staff_users = org.users.filter(is_active=True)
        
        # Get commission rules
        rules = CommissionRule.objects.filter(organization=org)

        # Variables to accumulate totals for the GL Posting
        total_gross = Decimal('0.00')
        total_napsa = Decimal('0.00')
        total_nhima = Decimal('0.00')
        total_paye = Decimal('0.00')
        total_net = Decimal('0.00')

        for staff in staff_users:
            # Skip if staff doesn't have a payroll profile
            if not hasattr(staff, 'payroll_profile'):
                continue 
            
            profile = staff.payroll_profile
            
            # 1. Base Pay
            basic_pay = profile.base_salary
            commission_pay = Decimal('0.00')
            
            # 2. Calculate Commission
            rule = rules.filter(role=staff.role).first()
            if rule:
                # Commission on Collections (Payments received during this period)
                collections = Payment.objects.filter(
                    loan__loan_officer=staff, 
                    received_at__date__range=(start_date, end_date),
                    is_reversed=False
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                
                commission_pay += collections * (rule.percentage_of_collections / 100)

                # Commission on Disbursements (Loans disbursed during this period)
                disbursed = Loan.objects.filter(
                    loan_officer=staff,
                    start_date__range=(start_date, end_date),
                    status__in=['ACTIVE', 'CLOSED', 'DISBURSED']
                ).aggregate(total=Sum('principal_amount'))['total'] or Decimal('0.00')
                
                commission_pay += disbursed * (rule.percentage_of_disbursed / 100)

            # 3. Totals
            gross_pay = basic_pay + commission_pay
            napsa, nhima, paye = PayrollService.calculate_statutory_deductions(gross_pay)
            total_deductions = napsa + nhima + paye
            net_pay = gross_pay - total_deductions

            # 4. Create or Update Payslip
            Payslip.objects.update_or_create(
                payroll_run=payroll_run,
                staff=staff,
                defaults={
                    'basic_pay': basic_pay,
                    'commission_pay': commission_pay,
                    'total_gross_pay': gross_pay,
                    'napsa_deduction': napsa,
                    'nhima_deduction': nhima,
                    'paye_tax': paye,
                    'total_deductions': total_deductions,
                    'net_pay': net_pay,
                }
            )

            # Accumulate for the GL Journal Entry
            total_gross += gross_pay
            total_napsa += napsa
            total_nhima += nhima
            total_paye += paye
            total_net += net_pay

        # ==========================================
        # 5. GL POSTING (Double-Entry Accounting)
        # ==========================================
        try:
            settings = org.payroll_settings
            
            # Create the Journal Entry header
            journal = JournalEntry.objects.create(
                organization=org,
                entry_date=period.payment_date,  # The actual date the money leaves the bank
                reference=f"PAYROLL-{period.name.replace(' ', '-')}",
                description=f"Payroll processing for {period.name}",
                source_type='Payroll',           # Make sure 'Payroll' is in SOURCE_TYPE_CHOICES in accounting/models.py
                source_id=payroll_run.id,
                created_by=user,
                is_posted=True
            )

            # DEBITS (Expenses)
            JournalLine.objects.create(
                journal_entry=journal, 
                account=settings.salary_expense_account, 
                debit=total_gross, 
                memo="Total Gross Pay"
            )
            
            # CREDITS (Liabilities & Bank)
            JournalLine.objects.create(
                journal_entry=journal, 
                account=settings.paye_payable_account, 
                credit=total_paye, 
                memo="PAYE Payable"
            )
            JournalLine.objects.create(
                journal_entry=journal, 
                account=settings.napsa_payable_account, 
                credit=total_napsa, 
                memo="NAPSA Payable"
            )
            JournalLine.objects.create(
                journal_entry=journal, 
                account=settings.nhima_payable_account, 
                credit=total_nhima, 
                memo="NHIMA Payable"
            )
            JournalLine.objects.create(
                journal_entry=journal, 
                account=settings.bank_account.gl_account, 
                credit=total_net, 
                memo="Net Pay via Bank"
            )
            
        except PayrollSetting.DoesNotExist:
            # By raising an exception here, the @transaction.atomic decorator 
            # will rollback all Payslips generated above so they don't save as orphans.
            raise Exception("Payroll GL Settings are missing. Please configure Chart of Accounts mapping in Payroll Settings.")

        # ==========================================
        # 6. FINALIZE
        # ==========================================
        
        # Lock the period so it can't be run again
        period.is_closed = True
        period.save()

        payroll_run.status = 'COMPLETED'
        payroll_run.processed_by = user
        payroll_run.save()
        
        return True

    @staticmethod
    def generate_bank_file(payroll_run: PayrollRun):
        """Generates a CSV file for bank bulk upload."""
        # Only pull staff with a bank account number
        payslips = payroll_run.payslips.select_related('staff__payroll_profile').all()
        
        response = HttpResponse(content_type='text/csv')
        filename = f"payroll_{payroll_run.period.name.replace(' ', '_')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        # Adjust these headers based on what your specific bank (Zanaco, FNB, ABSA) requires
        writer.writerow(['Account Name', 'Account Number', 'Bank Name', 'Amount', 'Reference'])
        
        for p in payslips:
            profile = p.staff.payroll_profile
            if profile.bank_account_number and p.net_pay > 0:
                writer.writerow([
                    f"{p.staff.first_name} {p.staff.last_name}",
                    profile.bank_account_number,
                    profile.bank_name or 'Unknown',
                    p.net_pay,
                    f"SAL {payroll_run.period.name}"
                ])
                
        return response