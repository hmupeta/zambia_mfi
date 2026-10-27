from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.loans.models import LoanProduct
from apps.origination.models import WorkflowTemplate, WorkflowStage


TEMPLATES = [
    {
        'name': 'Standard Loan Workflow',
        'description': 'Default 2-stage approval for most products.',
        'is_default': True,
        'loan_product': None,
        'stages': [
            {'order': 1, 'name': 'Loan Officer Review',
             'role_required': 'LOAN_OFFICER', 'sla_hours': 24, 'is_final': False},
            {'order': 2, 'name': 'Branch Manager Approval',
             'role_required': 'BRANCH_MANAGER', 'sla_hours': 48, 'is_final': True},
        ],
    },
    {
        'name': 'Large Loan Workflow',
        'description': '3-stage approval including HQ for loans above K50,000.',
        'loan_product': None,
        'min_amount': 50000,
        'stages': [
            {'order': 1, 'name': 'Loan Officer Review',
             'role_required': 'LOAN_OFFICER', 'sla_hours': 24, 'is_final': False},
            {'order': 2, 'name': 'Branch Manager Recommendation',
             'role_required': 'BRANCH_MANAGER', 'sla_hours': 48, 'is_final': False},
            {'order': 3, 'name': 'HQ Credit Committee',
             'role_required': 'HQ_ADMIN', 'sla_hours': 72, 'is_final': True},
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed default workflow templates for each organization.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        for org in orgs:
            self.stdout.write(f'\nSeeding workflows for {org.code}...')
            for spec in TEMPLATES:
                stages = spec.pop('stages', [])
                spec['organization'] = org
                template, created = WorkflowTemplate.objects.update_or_create(
                    organization=org,
                    name=spec['name'],
                    defaults=spec,
                )
                WorkflowStage.objects.filter(template=template).delete()
                for s in stages:
                    WorkflowStage.objects.create(template=template, **s)
                self.stdout.write(
                    f'  {"created" if created else "updated"}: {template.name} '
                    f'({len(stages)} stages)'
                )
                spec['stages'] = stages  # restore for next iteration

        self.stdout.write(self.style.SUCCESS('\n✅ Workflow seeding complete.'))