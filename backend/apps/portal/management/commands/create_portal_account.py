# apps/portal/management/commands/create_portal_account.py
"""Create or reset a client portal account.

Usage:
    python manage.py create_portal_account --phone 0971234567 --password secret123
    python manage.py create_portal_account --nrc 123456/11/1 --password secret123
    python manage.py create_portal_account --all --default-password ChangeMe123
"""
import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.portal.auth import create_account_for_client


class Command(BaseCommand):
    help = 'Create or reset a client portal account'

    def add_arguments(self, parser):
        parser.add_argument('--phone', type=str, help='Client phone number')
        parser.add_argument('--nrc', type=str, help='Client NRC')
        parser.add_argument('--password', type=str, help='Password to set')
        parser.add_argument('--all', action='store_true', help='Create accounts for all active clients')
        parser.add_argument('--default-password', type=str, default=None, help='Default password when using --all')

    def handle(self, *args, **opts):
        if opts['all']:
            pw = opts['default_password'] or secrets.token_urlsafe(8)
            clients = Client.objects.filter(is_active=True)
            count = 0
            for c in clients:
                create_account_for_client(c, pw)
                count += 1
                self.stdout.write(f'  {c.phone or c.nrc or c.id} — {c.first_name} {c.last_name}')
            self.stdout.write(self.style.SUCCESS(f'Created {count} accounts. Default password: {pw}'))
            return

        client = None
        if opts['phone']:
            client = Client.objects.filter(phone=opts['phone']).first()
        elif opts['nrc']:
            client = Client.objects.filter(nrc=opts['nrc']).first()
        else:
            raise CommandError('Provide --phone, --nrc, or --all')

        if not client:
            raise CommandError('Client not found.')

        pw = opts['password'] or secrets.token_urlsafe(8)
        create_account_for_client(client, pw)
        self.stdout.write(self.style.SUCCESS(
            f'Portal account ready for {client.first_name} {client.last_name} '
            f'({client.phone}). Password: {pw}'
        ))