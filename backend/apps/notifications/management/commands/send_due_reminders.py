from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Organization
from apps.loans.models import LoanInstallment
from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = 'Send payment-due reminders for installments due in N days.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')
        parser.add_argument('--days', type=int, default=None,
                            help='Days before due (defaults to settings).')

    def handle(self, *args, **options):
        days_before = options['days'] or \
            (settings.NOTIFICATIONS or {}).get('DUE_REMINDER_DAYS_BEFORE', 3)
        target_date = timezone.now().date() + timedelta(days=days_before)

        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        total_sent = 0
        for org in orgs:
            installments = LoanInstallment.objects.filter(
                loan__organization=org,
                due_date=target_date,
                is_paid=False,
                status__in=['PENDING', 'PARTIAL'],
            ).select_related('loan', 'loan__client')

            self.stdout.write(
                f"\n{org.code}: {installments.count()} installment(s) due on {target_date}"
            )
            for inst in installments:
                # Skip if we already sent a reminder for this installment today
                from apps.notifications.models import NotificationLog
                already = NotificationLog.objects.filter(
                    organization=org,
                    source_type='LoanInstallment',
                    source_id=inst.id,
                    template_code='PAYMENT_DUE',
                    created_at__date=timezone.now().date(),
                ).exists()
                if already:
                    continue

                NotificationService.on_installment_due_soon(inst, days_before=days_before)
                total_sent += 1

        self.stdout.write(self.style.SUCCESS(f'\n✅ Sent {total_sent} reminder(s).'))