"""
Bootstrap the platform admin account.

Usage:
    python manage.py seed_platform
    python manage.py seed_platform --username=platform-admin --email=admin@example.com
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = 'Create or update the platform admin user.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='platform-admin')
        parser.add_argument('--email', default='platform@zambiamfi.local')
        parser.add_argument('--password', default='PlatformAdmin@2026')

    @transaction.atomic
    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email},
        )

        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_platform_admin = True
        user.role = 'HQ_ADMIN'
        user.organization = None
        user.branch = None
        user.set_password(password)
        user.save()

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'✅ {action} platform admin:\n'
            f'   Username: {username}\n'
            f'   Email:    {email}\n'
            f'   Password: {password}\n'
            f'   ⚠️  Change the password after first login.'
        ))