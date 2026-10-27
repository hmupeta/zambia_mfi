"""
Create a new MFI tenant with HQ branch, HQ admin user, and default loan products.

Usage:
    python manage.py create_tenant --code=acme-mfi --name="Acme Microfinance"
    python manage.py create_tenant --code=acme-mfi --name="Acme" --admin-username=acme-admin
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal

from apps.core.models import Organization, Branch
from apps.loans.models import LoanProduct

User = get_user_model()


# Default loan products seeded for every new tenant
DEFAULT_LOAN_PRODUCTS = [
    {
        'code': 'SME',
        'name': 'Small Business Loan',
        'min_amount': Decimal('500'),
        'max_amount': Decimal('50000'),
        'min_tenure_months': 1,
        'max_tenure_months': 12,
        'interest_rate': Decimal('2.50'),
        'interest_method': 'FLAT',
        'repayment_frequency': 'WEEKLY',
    },
    {
        'code': 'AGRI',
        'name': 'Agricultural Loan',
        'min_amount': Decimal('1000'),
        'max_amount': Decimal('100000'),
        'min_tenure_months': 3,
        'max_tenure_months': 18,
        'interest_rate': Decimal('2.00'),
        'interest_method': 'REDUCING_BALANCE',
        'repayment_frequency': 'MONTHLY',
    },
    {
        'code': 'EMERG',
        'name': 'Emergency Loan',
        'min_amount': Decimal('200'),
        'max_amount': Decimal('5000'),
        'min_tenure_months': 1,
        'max_tenure_months': 3,
        'interest_rate': Decimal('3.00'),
        'interest_method': 'FLAT',
        'repayment_frequency': 'WEEKLY',
    },
]


class Command(BaseCommand):
    help = 'Create a new tenant organization with HQ branch, admin user, and default loan products.'

    def add_arguments(self, parser):
        parser.add_argument('--code', required=True, help='Short slug, e.g., acme-mfi')
        parser.add_argument('--name', required=True, help='Display name, e.g., Acme Microfinance Zambia')
        parser.add_argument('--email', default='', help='Contact email for the org')
        parser.add_argument('--phone', default='', help='Contact phone')
        parser.add_argument('--tier', default='TRIAL',
                            choices=['TRIAL', 'BASIC', 'PRO', 'ENTERPRISE'])
        parser.add_argument('--admin-username', default=None,
                            help='HQ admin username (defaults to <code>-admin)')
        parser.add_argument('--admin-email', default=None)
        parser.add_argument('--admin-password', default='TenantAdmin@2026')

    @transaction.atomic
    def handle(self, *args, **options):
        code = options['code']
        name = options['name']

        if Organization.objects.filter(code=code).exists():
            raise CommandError(f"Organization with code '{code}' already exists.")

        # 1. Organization
        org = Organization.objects.create(
            code=code,
            name=name,
            legal_name=name,
            email=options['email'],
            phone=options['phone'],
            subscription_tier=options['tier'],
            is_active=True,
        )
        self.stdout.write(self.style.SUCCESS(f'✅ Organization created: {org.code}'))

        # 2. HQ Branch
        hq = Branch.objects.create(
            organization=org,
            code='HQ-001',
            name='Headquarters',
            is_hq=True,
            physical_address='Update HQ address',
        )
        self.stdout.write(self.style.SUCCESS(f'✅ HQ branch created: {hq.code}'))

        # 3. HQ Admin user
        admin_username = options['admin_username'] or f'{code}-admin'
        admin_email = options['admin_email'] or options['email'] or f'{admin_username}@local'

        if User.objects.filter(username=admin_username).exists():
            raise CommandError(f"User '{admin_username}' already exists.")

        admin = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=options['admin_password'],
            organization=org,
            branch=hq,
            role='HQ_ADMIN',
            is_staff=True,
        )
        self.stdout.write(self.style.SUCCESS(f'✅ HQ admin created: {admin.username}'))

        # 4. Default loan products
        for spec in DEFAULT_LOAN_PRODUCTS:
            LoanProduct.objects.create(organization=org, **spec)
        self.stdout.write(self.style.SUCCESS(
            f'✅ {len(DEFAULT_LOAN_PRODUCTS)} loan products seeded'
        ))

        self.stdout.write(self.style.SUCCESS('\n🎉 Tenant ready!\n'))
        self.stdout.write(f'   Organization code: {org.code}')
        self.stdout.write(f'   Admin username:    {admin.username}')
        self.stdout.write(f'   Admin password:    {options["admin_password"]}')
        self.stdout.write(f'   Login via:         POST /api/auth/token/')