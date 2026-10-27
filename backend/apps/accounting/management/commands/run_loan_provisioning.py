from datetime import date
from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.accounting.services_provisioning import ProvisioningService


class Command(BaseCommand):
    help = 'Run BoZ loan loss provisioning for all active tenants.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')
        parser.add_argument('--as-of', help='YYYY-MM-DD (defaults to today).')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        as_of = date.fromisoformat(options['as_of']) if options['as_of'] else date.today()

        for org in orgs:
            self.stdout.write(f"\nProcessing {org.code}...")
            summary = ProvisioningService.run_for_organization(org, as_of_date=as_of)
            self.stdout.write(self.style.SUCCESS(
                f"  Loans processed: {summary['loans_processed']}\n"
                f"  Total provision: {summary['total_provision']}\n"
                f"  Provision movement: {summary['total_movement']}"
            ))
            for cls, count in summary['by_classification'].items():
                self.stdout.write(f"    {cls}: {count}")

        self.stdout.write(self.style.SUCCESS('\n✅ Provisioning run complete.'))