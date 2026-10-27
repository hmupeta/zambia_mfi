# apps/momo/management/commands/test_provider.py
"""
Test a mobile money provider's credentials without touching the DB.

Usage:
    python manage.py test_provider KAZANG
    python manage.py test_provider BROADPAY --amount 1 --phone 0971234567
    python manage.py test_provider --all          # test every configured provider
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Organization
from apps.momo.models import MomoProviderConfig
from apps.momo.providers.base import get_provider, MomoProviderError


class Command(BaseCommand):
    help = 'Verify mobile money provider credentials'

    def add_arguments(self, parser):
        parser.add_argument('provider', nargs='?', type=str, help='Provider code (e.g. KAZANG)')
        parser.add_argument('--org', type=str, help='Organization code (default: first)')
        parser.add_argument('--all', action='store_true', help='Test every configured provider')
        parser.add_argument('--phone', type=str, default='0971234567', help='Test phone number')
        parser.add_argument('--amount', type=str, default='1', help='Test amount')

    def handle(self, *args, **opts):
        org_code = opts.get('org')
        org = (
            Organization.objects.filter(code=org_code).first()
            if org_code else Organization.objects.first()
        )
        if not org:
            raise CommandError('No organization found.')

        if opts['all']:
            configs = MomoProviderConfig.objects.filter(organization=org, is_active=True)
        elif opts['provider']:
            configs = MomoProviderConfig.objects.filter(
                organization=org,
                provider_code=opts['provider'].upper(),
                is_active=True,
            )
            if not configs.exists():
                raise CommandError(
                    f'No active config for provider {opts["provider"].upper()}.'
                )
        else:
            raise CommandError('Provide a provider code or use --all.')

        self.stdout.write(f'\nTesting for org: {org.code}\n')

        for cfg in configs:
            self._test_one(cfg, opts['phone'], Decimal(opts['amount']))

    def _test_one(self, cfg, phone, amount):
        self.stdout.write('=' * 60)
        self.stdout.write(f'Provider: {cfg.provider_code}  ({cfg.display_name or "—"})')
        self.stdout.write(f'Sandbox:  {cfg.is_sandbox}')

        if cfg.provider_code == 'FAKE':
            self.stdout.write(self.style.SUCCESS('  ✓ Fake provider — nothing to test.\n'))
            return

        try:
            provider = get_provider(cfg)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Adapter failed to load: {e}\n'))
            return

        # --- Test collect ---
        self.stdout.write('  Testing collect()…')
        try:
            result = provider.collect(
                reference=f'TEST-{cfg.provider_code[:6]}',
                amount=amount,
                phone=phone,
                description='Test connection',
            )
            txn = result.get('provider_txn_id', '')
            status = result.get('status', '?')
            redirect = result.get('redirect_url', '')

            self.stdout.write(self.style.SUCCESS(
                f'  ✓ collect() succeeded — txn={txn[:20]}  status={status}'
            ))
            if redirect:
                self.stdout.write(f'      redirect_url: {redirect[:80]}')
        except NotImplementedError:
            self.stdout.write(self.style.WARNING('  ⚠ collect() not implemented for this provider.'))
        except MomoProviderError as e:
            self.stdout.write(self.style.ERROR(f'  ✗ collect() failed: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Unexpected error: {type(e).__name__}: {e}'))

        # --- Test disburse ---
        self.stdout.write('  Testing disburse()…')
        try:
            result = provider.disburse(
                reference=f'TEST-PAYOUT-{cfg.provider_code[:6]}',
                amount=amount,
                phone=phone,
                description='Test payout',
            )
            txn = result.get('provider_txn_id', '')
            status = result.get('status', '?')
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ disburse() succeeded — txn={txn[:20]}  status={status}'
            ))
        except NotImplementedError:
            self.stdout.write(self.style.WARNING('  ⚠ disburse() not implemented for this provider.'))
        except MomoProviderError as e:
            self.stdout.write(self.style.ERROR(f'  ✗ disburse() failed: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Unexpected error: {type(e).__name__}: {e}'))

        self.stdout.write('')