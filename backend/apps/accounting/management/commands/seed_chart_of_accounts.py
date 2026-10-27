from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.accounting.models import GLAccount


CHART = [
    # ASSETS
    ('1000', 'Cash and Cash Equivalents', 'ASSET', None),
    ('1010', 'Cash on Hand - Branch', 'ASSET', '1000'),
    ('1020', 'Bank Account - Operating', 'ASSET', '1000'),
    ('1030', 'Mobile Money Account', 'ASSET', '1000'),
    ('1100', 'Loans Receivable - Principal', 'ASSET', None),
    ('1110', 'Loans Receivable - Interest', 'ASSET', None),
    ('1120', 'Loans Receivable - Penalties', 'ASSET', None),
    ('1130', 'Interest Receivable (Accrued)', 'ASSET', None),
    ('1200', 'Allowance for Loan Losses', 'ASSET', None),
    ('1300', 'Office Equipment', 'ASSET', None),
    ('1310', 'Accumulated Depreciation - Equipment', 'ASSET', '1300'),

    # LIABILITIES
    ('2000', 'Accounts Payable', 'LIABILITY', None),
    ('2100', 'Interest in Suspense', 'LIABILITY', None),
    ('2200', 'Client Savings', 'LIABILITY', None),
    ('2300', 'Loan Loss Provision', 'LIABILITY', None),

    # EQUITY
    ('3000', 'Share Capital', 'EQUITY', None),
    ('3100', 'Retained Earnings', 'EQUITY', None),

    # INCOME
    ('4000', 'Interest Income - Loans', 'INCOME', None),
    ('4100', 'Penalty Income', 'INCOME', None),
    ('4200', 'Fee Income', 'INCOME', None),
    ('4300', 'Recovery Income', 'INCOME', None),

    # EXPENSES
    ('5000', 'Loan Loss Expense', 'EXPENSE', None),
    ('5100', 'Interest Expense', 'EXPENSE', None),
    ('5200', 'Operating Expenses', 'EXPENSE', None),
    ('5300', 'Salaries and Wages', 'EXPENSE', None),
]


class Command(BaseCommand):
    help = 'Seed the standard Chart of Accounts for every active organization.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code. If omitted, all active orgs are seeded.')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        if not orgs.exists():
            self.stdout.write(self.style.WARNING('No organizations found.'))
            return

        for org in orgs:
            self.stdout.write(f"\nSeeding Chart of Accounts for {org.code}...")
            code_map = {}   # code -> GLAccount instance
            created_count = 0

            for code, name, atype, parent_code in CHART:
                parent = code_map.get(parent_code) if parent_code else None
                obj, created = GLAccount.objects.get_or_create(
                    organization=org,
                    code=code,
                    defaults={
                        'name': name,
                        'account_type': atype,
                        'parent': parent,
                        'is_contra': code in ('1200', '1310'),
                    },
                )
                code_map[code] = obj
                if created:
                    created_count += 1

            self.stdout.write(self.style.SUCCESS(
                f'  ✅ {created_count} accounts created, {len(CHART) - created_count} already existed.'
            ))

        self.stdout.write(self.style.SUCCESS('\n🎉 Chart of Accounts seeding complete.'))