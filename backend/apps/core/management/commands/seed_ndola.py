# apps/core/management/commands/seed_ndola.py
import random
from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.core.models import Organization, Branch, User
from apps.payroll.models import StaffProfile

try:
    from apps.clients.models import Client
    from apps.loans.models import Loan
    from apps.payments.models import Payment
except ImportError:
    pass

class Command(BaseCommand):
    help = 'Seeds the Ndola branch with staff, clients, and active loans'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Starting Ndola Branch Seeding..."))
        
        org = Organization.objects.filter(code="acme-mfi").first()
        if not org:
            self.stdout.write(self.style.ERROR("Organization 'acme-mfi' not found."))
            return

        # 1. CREATE NDOLA BRANCH
        ndola, _ = Branch.objects.get_or_create(
            organization=org, code="NDL-001", 
            defaults={'name': "Ndola Branch"}
        )

        # 2. CREATE NDOLA STAFF
        users_data = [
            ("ndola_mgr", "Patrick", "Mwewa", "BRANCH_MANAGER", 14000, "Zanaco"),
            ("ndola_lo1", "Agnes", "Chileshe", "LOAN_OFFICER", 5500, "FNB"),
            ("ndola_lo2", "Brian", "Kunda", "LOAN_OFFICER", 5200, "ABSA"),
            ("ndola_tel", "Faith", "Musonda", "TELLER", 4800, "Zanaco"),
        ]
        
        for username, first, last, role, salary, bank in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f"{username}@acme.com", 'first_name': first, 'last_name': last,
                    'role': role, 'organization': org, 'branch': ndola, 'is_staff': True
                }
            )
            if created:
                user.set_password("password123")
                user.save()
            
            StaffProfile.objects.get_or_create(
                user=user, 
                defaults={'base_salary': salary, 'bank_name': bank, 'bank_account_number': f"00{random.randint(1000000, 9999999)}"}
            )
        self.stdout.write("Created Ndola Staff & Payroll Profiles.")

        # 3. CREATE NDOLA CLIENTS
        first_names = ["Chanda", "Mutale", "Moses", "Lweendo", "Thandiwe", "Kelvin", "Dorothy", "Isaac", "Precious", "Gift"]
        last_names = ["Bwalya", "Musonda", "Kambole", "Chola", "Sakala", "Mwanza", "Siame", "Nkandu", "Chanda", "Mbewe"]
        
        clients = []
        for i in range(25):
            random_nrc = f"{random.randint(100000, 999999)}/{random.randint(10, 99)}/{random.randint(1, 9)}"
            c = Client.objects.create(
                organization=org, branch=ndola,
                first_name=random.choice(first_names), last_name=random.choice(last_names),
                phone=f"0977{random.randint(100000, 999999)}",
                nrc=random_nrc,
            )
            clients.append(c)
        self.stdout.write("Created 25 Clients for Ndola.")

        # 4. DYNAMIC FIELD DETECTION
        loan_fields = [f.name for f in Loan._meta.get_fields()]
        payment_fields = [f.name for f in Payment._meta.get_fields()]
        
        # Figure out the exact field names for amounts and dates
        amount_field = next((f for f in ['principal_amount', 'amount', 'principal', 'loan_amount'] if f in loan_fields), 'amount')
        date_field = next((f for f in ['start_date', 'disbursement_date', 'date_disbursed'] if f in loan_fields), 'start_date')
        
        pay_amount_field = next((f for f in ['amount', 'payment_amount'] if f in payment_fields), 'amount')
        pay_date_field = next((f for f in ['received_at', 'payment_date', 'date_paid'] if f in payment_fields), 'received_at')

        # 5. CREATE LOANS & PAYMENTS
        officers = [User.objects.get(username="ndola_lo1"), User.objects.get(username="ndola_lo2")]
        
        for client in clients:
            officer = random.choice(officers)
            principal = Decimal(random.randint(3000, 20000))
            interest_rate = Decimal('15.00')
            total_interest = principal * (interest_rate / 100)
            total_amount = principal + total_interest
            
            # Build the Loan dictionary
            loan_kwargs = {
                'organization': org, 
                'branch': ndola, 
                'client': client, 
                'loan_officer': officer,
                'status': "ACTIVE",
                amount_field: principal,
                date_field: timezone.now().date() - timedelta(days=random.randint(30, 120)),
            }
            
            # Safely add financial fields if they exist in your model
            if 'loan_number' in loan_fields: loan_kwargs['loan_number'] = f"LN-{random.randint(100000, 999999)}"
            if 'interest_rate' in loan_fields: loan_kwargs['interest_rate'] = interest_rate
            if 'term_months' in loan_fields: loan_kwargs['term_months'] = 6
            if 'total_interest' in loan_fields: loan_kwargs['total_interest'] = total_interest
            if 'total_amount' in loan_fields: loan_kwargs['total_amount'] = total_amount
            if 'outstanding_balance' in loan_fields: loan_kwargs['outstanding_balance'] = total_amount
            
            loan = Loan.objects.create(**loan_kwargs)
            
            # Create random payments
            num_payments = random.randint(1, 4)
            for p in range(num_payments):
                pay_amt = Decimal(random.randint(500, int(total_amount / 2)))
                pay_kwargs = {
                    'organization': org, 
                    'branch': ndola, 
                    'loan': loan, 
                    'is_reversed': False,
                    pay_amount_field: pay_amt,
                    pay_date_field: timezone.now() - timedelta(days=random.randint(1, 25)),
                }
                
                # Safely add standard payment fields if they exist
                if 'payment_method' in payment_fields: pay_kwargs['payment_method'] = 'CASH'
                if 'receipt_number' in payment_fields: pay_kwargs['receipt_number'] = f"RCT{random.randint(1000, 9999)}"
                if 'principal_paid' in payment_fields: pay_kwargs['principal_paid'] = pay_amt * Decimal('0.8')
                if 'interest_paid' in payment_fields: pay_kwargs['interest_paid'] = pay_amt * Decimal('0.2')
                if 'balance_before' in payment_fields: pay_kwargs['balance_before'] = total_amount
                if 'balance_after' in payment_fields: pay_kwargs['balance_after'] = total_amount - pay_amt
                
                Payment.objects.create(**pay_kwargs)
                
        self.stdout.write(self.style.SUCCESS(f"✅ Created {len(clients)} Active Loans with Payments for Ndola."))
        self.stdout.write("Usernames: ndola_mgr, ndola_lo1, ndola_lo2, ndola_tel (Password: password123)")