"""
Seed demo data for a tenant: extra branches, staff, clients, and loans.

Usage:
    python manage.py seed_demo_data --org=acme-mfi
    python manage.py seed_demo_data --org=acme-mfi --clients=20 --loans=10
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.models import Organization, Branch
from apps.clients.models import Client
from apps.loans.models import Loan, LoanProduct
from apps.loans.services import LoanService

User = get_user_model()


ZAMBIAN_FIRST_NAMES = ['John', 'Mary', 'Peter', 'Grace', 'Chanda', 'Mutale', 'Bwalya', 'Thandiwe', 'Emmanuel', 'Ruth']
ZAMBIAN_LAST_NAMES = ['Mwansa', 'Banda', 'Phiri', 'Tembo', 'Mulenga', 'Zulu', 'Chanda', 'Sakala', 'Nkomo', 'Mbewe']
PROVINCES = ['Lusaka', 'Copperbelt', 'Southern', 'Central', 'Eastern', 'Northern']


class Command(BaseCommand):
    help = 'Seed demo data (branches, users, clients, loans) for a tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--org', required=True, help='Organization code')
        parser.add_argument('--clients', type=int, default=10)
        parser.add_argument('--loans', type=int, default=5)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(code=options['org'])
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{options['org']}' not found.")

        hq = org.branches.filter(is_hq=True).first()
        if not hq:
            raise CommandError(f"HQ branch not found for org {org.code}.")

        # ---------- 1. Extra branches ----------
        extra_branches = ['LUS-01', 'NDL-01', 'KIT-01']
        branches = [hq]
        for code in extra_branches:
            b, _ = Branch.objects.get_or_create(
                organization=org,
                code=code,
                defaults={
                    'name': f'{code} Branch',
                    'physical_address': f'{code} Address',
                },
            )
            branches.append(b)
        self.stdout.write(self.style.SUCCESS(f'✅ Branches: {len(branches)}'))

        # ---------- 2. Staff users ----------
        staff_specs = [
            ('manager-lus', 'BRANCH_MANAGER', branches[1]),
            ('officer-lus', 'LOAN_OFFICER', branches[1]),
            ('teller-lus', 'TELLER', branches[1]),
            ('manager-ndl', 'BRANCH_MANAGER', branches[2]),
            ('officer-ndl', 'LOAN_OFFICER', branches[2]),
        ]
        staff = []
        for uname, role, branch in staff_specs:
            full_uname = f'{org.code}-{uname}'
            u, created = User.objects.get_or_create(
                username=full_uname,
                defaults={
                    'email': f'{full_uname}@local',
                    'organization': org,
                    'branch': branch,
                    'role': role,
                },
            )
            if created:
                u.set_password('Staff@2026')
                u.save()
            staff.append(u)
        self.stdout.write(self.style.SUCCESS(f'✅ Staff users: {len(staff)}'))

        # ---------- 3. Clients ----------
        existing_clients = Client.objects.filter(organization=org).count()
        to_create = max(0, options['clients'] - existing_clients)

        clients = list(Client.objects.filter(organization=org))
        for i in range(to_create):
            branch = random.choice(branches)
            first = random.choice(ZAMBIAN_FIRST_NAMES)
            last = random.choice(ZAMBIAN_LAST_NAMES)
            nrc = f"{random.randint(100000,999999)}-{random.randint(10,99)}-{random.randint(1,9)}"
            c = Client.objects.create(
                organization=org,
                branch=branch,
                nrc=nrc,
                first_name=first,
                last_name=last,
                gender=random.choice(['M', 'F']),
                phone=f"+2609{random.randint(10000000, 99999999)}",
                occupation=random.choice(['Trader', 'Farmer', 'Shopkeeper', 'Teacher']),
                province=random.choice(PROVINCES),
                kyc_status='VERIFIED',
                created_by=random.choice(staff),
            )
            clients.append(c)
        self.stdout.write(self.style.SUCCESS(f'✅ Clients total: {len(clients)}'))

        # ---------- 4. Loans ----------
        existing_loans = Loan.objects.filter(organization=org).count()
        to_create_loans = max(0, options['loans'] - existing_loans)

        products = list(LoanProduct.objects.filter(organization=org, is_active=True))
        if not products:
            raise CommandError("No loan products for org.")

        for i in range(to_create_loans):
            product = random.choice(products)
            client = random.choice(clients)
            amount = Decimal(random.randint(
                int(product.min_amount), int(product.max_amount)
            ))

            start = timezone.now().date()
            maturity = start + timedelta(days=product.max_tenure_months * 30)

            loan = Loan.objects.create(
                organization=org,
                loan_number=f'LN-{org.code.upper()}-{start.strftime("%Y%m%d")}-{i+1:04d}',
                branch=client.branch,
                client=client,
                loan_product=product,
                loan_officer=random.choice(staff),
                amount=amount,
                total_interest=Decimal('0'),
                total_amount_due=Decimal('0'),
                balance_due=Decimal('0'),
                start_date=start,
                maturity_date=maturity,
                interest_rate=product.interest_rate,
                interest_method=product.interest_method,
                repayment_frequency=product.repayment_frequency,
                status='PENDING',
            )
            LoanService.generate_installments(loan)

        self.stdout.write(self.style.SUCCESS(
            f'✅ Loans: {Loan.objects.filter(organization=org).count()}'
        ))
        self.stdout.write(self.style.SUCCESS('\n🎉 Demo data seeded successfully.\n'))
        self.stdout.write('Test credentials:')
        self.stdout.write(f'   HQ admin:        {org.code}-admin / TenantAdmin@2026')
        self.stdout.write(f'   Branch manager:  {org.code}-manager-lus / Staff@2026')
        self.stdout.write(f'   Loan officer:    {org.code}-officer-lus / Staff@2026')
        self.stdout.write(f'   Teller:          {org.code}-teller-lus / Staff@2026')