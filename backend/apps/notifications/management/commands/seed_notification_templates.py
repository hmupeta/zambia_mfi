"""Seed default notification templates."""
from django.core.management.base import BaseCommand

from apps.core.models import Organization
from apps.notifications.models import NotificationTemplate


DEFAULTS = [
    ('payment_received', 'Payment Received', 'SMS', '',
     'Dear {{client_name}}, we have received your payment of K{{amount}} for loan {{loan_number}} on {{date}}. New balance: K{{balance_due}}. Thank you.'),
    ('loan_disbursed', 'Loan Disbursed', 'SMS', '',
     'Dear {{client_name}}, your loan {{loan_number}} of K{{amount}} has been disbursed. First payment due {{first_due_date}}. Thank you.'),
    ('due_reminder_3d', 'Due Reminder (3 days)', 'SMS', '',
     'Dear {{client_name}}, a payment of K{{amount}} for loan {{loan_number}} is due on {{due_date}}. Please ensure funds are ready.'),
    ('due_reminder_1d', 'Due Reminder (1 day)', 'SMS', '',
     'Dear {{client_name}}, reminder: K{{amount}} due TOMORROW ({{due_date}}) for loan {{loan_number}}.'),
    ('due_reminder_0d', 'Due Reminder (today)', 'SMS', '',
     'Dear {{client_name}}, your payment of K{{amount}} for loan {{loan_number}} is due TODAY. Please pay to avoid penalties.'),
    ('overdue_notice', 'Overdue Notice', 'SMS', '',
     'Dear {{client_name}}, your payment of K{{amount}} for loan {{loan_number}} was due on {{due_date}} and is now overdue. Please pay immediately.'),
    ('kyc_approved', 'KYC Verified', 'SMS', '',
     'Dear {{client_name}}, your KYC verification is complete. You can now apply for loans.'),
    ('application_approved', 'Application Approved', 'SMS', '',
     'Dear {{client_name}}, your loan application {{application_number}} for K{{amount}} has been approved. We will contact you shortly.'),

    ('payment_received_email', 'Payment Received (Email)', 'EMAIL',
     'Payment confirmation - {{org_name}}',
     'Dear {{client_name}},\n\nWe have received your payment of K{{amount}} for loan {{loan_number}} on {{date}}.\n\nNew outstanding balance: K{{balance_due}}\n\nThank you.\n\nRegards,\n{{org_name}}'),
    ('loan_disbursed_email', 'Loan Disbursed (Email)', 'EMAIL',
     'Your loan has been disbursed - {{org_name}}',
     'Dear {{client_name}},\n\nYour loan {{loan_number}} of K{{amount}} has been disbursed.\n\nFirst payment due date: {{first_due_date}}\n\nRegards,\n{{org_name}}'),
    ('due_reminder_email', 'Due Reminder (Email)', 'EMAIL',
     'Upcoming payment reminder - {{org_name}}',
     'Dear {{client_name}},\n\nThis is a friendly reminder that a payment of K{{amount}} for loan {{loan_number}} is due on {{due_date}}.\n\nRegards,\n{{org_name}}'),
    ('overdue_notice_email', 'Overdue Notice (Email)', 'EMAIL',
     'Overdue payment on loan {{loan_number}} - {{org_name}}',
     'Dear {{client_name}},\n\nYour payment of K{{amount}} for loan {{loan_number}} was due on {{due_date}} and is now overdue.\n\nPlease settle the outstanding balance as soon as possible.\n\nRegards,\n{{org_name}}'),
    ('kyc_approved_email', 'KYC Verified (Email)', 'EMAIL',
     'KYC verification complete - {{org_name}}',
     'Dear {{client_name}},\n\nWe are pleased to confirm that your KYC verification is complete.\n\nRegards,\n{{org_name}}'),
    ('application_approved_email', 'Application Approved (Email)', 'EMAIL',
     'Your loan application has been approved - {{org_name}}',
     'Dear {{client_name}},\n\nYour loan application {{application_number}} for K{{amount}} has been approved.\n\nRegards,\n{{org_name}}'),
]


class Command(BaseCommand):
    help = 'Seed default notification templates'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, help='Organization code (default: all)')

    def handle(self, *args, **options):
        qs = Organization.objects.all()
        if options.get('org'):
            qs = qs.filter(code=options['org'])

        total = 0
        for org in qs:
            for key, name, channel, subject, body in DEFAULTS:
                _, created = NotificationTemplate.objects.get_or_create(
                    organization=org, key=key,
                    defaults={
                        'name': name, 'channel': channel, 'subject': subject,
                        'body': body, 'is_active': True, 'is_system': True,
                    },
                )
                if created:
                    total += 1
                    self.stdout.write('  + %s / %s' % (org.code, key))

        self.stdout.write(self.style.SUCCESS('Created %d templates.' % total))
