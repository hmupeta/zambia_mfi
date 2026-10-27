from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Organization
from apps.loans.models import LoanInstallment
from apps.notifications.services import NotificationService
from apps.notifications.models import NotificationLog


class Command(BaseCommand):
    help = 'Send overdue notices for installments past their due date.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')

    def handle(self, *args, **options):
        today = timezone.now().date()
        reminder_days = (settings.NOTIFICATIONS or {}).get(
            'OVERDUE_REMINDER_DAYS', [1, 7, 30],
        )

        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        total_sent = 0
        for org in orgs:
            overdue = LoanInstallment.objects.filter(
                loan__organization=org,
                due_date__lt=today,
                is_paid=False,
                status__in=['PENDING', 'PARTIAL', 'OVERDUE'],
            ).select_related('loan', 'loan__client')

            self.stdout.write(f"\n{org.code}: {overdue.count()} overdue installment(s)")
            for inst in overdue:
                days_overdue = (today - inst.due_date).days

                # Only send on configured threshold days (1, 7, 30)
                if days_overdue not in reminder_days:
                    continue

                # Skip if we already notified today
                already = NotificationLog.objects.filter(
                    organization=org,
                    source_type='LoanInstallment',
                    source_id=inst.id,
                    template_code='OVERDUE_NOTICE',
                    created_at__date=today,
                ).exists()
                if already:
                    continue

                NotificationService.on_overdue(inst, days_overdue)
                total_sent += 1

        self.stdout.write(self.style.SUCCESS(f'\n✅ Sent {total_sent} overdue notice(s).'))