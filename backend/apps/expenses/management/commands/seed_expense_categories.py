from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.expenses.models import ExpenseCategory
from apps.accounting.models import GLAccount


# Standard MFI expense categories
CATEGORIES = [
    {
        'code': 'RENT',
        'name': 'Rent',
        'gl_code': '5200',
        'requires_approval': True,
        'threshold': None,
    },
    {
        'code': 'SAL',
        'name': 'Salaries and Wages',
        'gl_code': '5300',
        'requires_approval': True,
        'threshold': '5000.00',
    },
    {
        'code': 'UTIL',
        'name': 'Utilities (Water and Electricity)',
        'gl_code': '5200',
        'requires_approval': False,
        'threshold': None,
    },
    {
        'code': 'FUEL',
        'name': 'Fuel and Transport',
        'gl_code': '5200',
        'requires_approval': False,
        'threshold': None,
    },
    {
        'code': 'BANK',
        'name': 'Bank Charges',
        'gl_code': '5200',
        'requires_approval': False,
        'threshold': None,
    },
    {
        'code': 'LIC',
        'name': 'Licenses and Regulatory Fees',
        'gl_code': '5200',
        'requires_approval': True,
        'threshold': None,
    },
    {
        'code': 'OFFC',
        'name': 'Office Supplies',
        'gl_code': '5200',
        'requires_approval': False,
        'threshold': None,
    },
    {
        'code': 'TRVL',
        'name': 'Travel and Accommodation',
        'gl_code': '5200',
        'requires_approval': True,
        'threshold': None,
    },
]


class Command(BaseCommand):
    help = 'Seed standard expense categories for each organization.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        for org in orgs:
            self.stdout.write(f"\nSeeding expense categories for {org.code}...")
            created_count = 0

            for spec in CATEGORIES:
                try:
                    gl = GLAccount.objects.get(
                        organization=org, code=spec['gl_code'],
                    )
                except GLAccount.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"  Skipping {spec['code']}: GL account {spec['gl_code']} not found."
                    ))
                    continue

                obj, created = ExpenseCategory.objects.get_or_create(
                    organization=org,
                    code=spec['code'],
                    defaults={
                        'name': spec['name'],
                        'gl_account': gl,
                        'requires_approval': spec['requires_approval'],
                        'approval_threshold': spec['threshold'],
                    },
                )
                if created:
                    created_count += 1

            self.stdout.write(self.style.SUCCESS(
                f'  ✅ {created_count} new categories, {len(CATEGORIES) - created_count} already existed.'
            ))

        self.stdout.write(self.style.SUCCESS('\n🎉 Expense categories seeding complete.'))