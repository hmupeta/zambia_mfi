from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.kyc.models import KYCDocumentRequirement


REQUIREMENTS = [
    # --- Individuals ---
    {'code': 'NRC', 'name': 'National Registration Card',
     'document_type': 'NRC', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'allows_expiry': False, 'order': 10},
    {'code': 'PHOTO', 'name': 'Passport Photo',
     'document_type': 'PHOTO', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'order': 20},
    {'code': 'ADDR', 'name': 'Proof of Address',
     'document_type': 'ADDRESS_PROOF', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['MEDIUM', 'HIGH', 'PEP'],
     'is_mandatory': True, 'allows_expiry': True, 'expiry_reminder_days': 30,
     'order': 30},
    {'code': 'PAYSLIP', 'name': 'Payslip / Income Proof',
     'document_type': 'PAYSLIP', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['MEDIUM', 'HIGH', 'PEP'],
     'is_mandatory': False, 'order': 40},
    {'code': 'BNKST', 'name': 'Bank Statement (3 months)',
     'document_type': 'BANK_STATEMENT', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['HIGH', 'PEP'],
     'is_mandatory': True, 'order': 50},
    {'code': 'SELFIE', 'name': 'Selfie (for liveness check)',
     'document_type': 'SELFIE', 'client_type': 'INDIVIDUAL',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'order': 60},

    # --- Businesses ---
    {'code': 'BREG', 'name': 'Business Registration (PACRA)',
     'document_type': 'BUSINESS_REG', 'client_type': 'BUSINESS',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'order': 10},
    {'code': 'DIRID', 'name': "Directors' IDs",
     'document_type': 'NRC', 'client_type': 'BUSINESS',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'order': 20},
    {'code': 'BADDR', 'name': 'Business Address Proof',
     'document_type': 'ADDRESS_PROOF', 'client_type': 'BUSINESS',
     'required_for_risk_levels': ['ALL'], 'is_mandatory': True,
     'order': 30},
    {'code': 'BFIN', 'name': 'Financial Statements',
     'document_type': 'OTHER', 'client_type': 'BUSINESS',
     'required_for_risk_levels': ['MEDIUM', 'HIGH', 'PEP'],
     'is_mandatory': True, 'order': 40},
]


class Command(BaseCommand):
    help = 'Seed standard KYC document requirements for each org.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        for org in orgs:
            self.stdout.write(f'\nSeeding KYC requirements for {org.code}...')
            created = 0
            for spec in REQUIREMENTS:
                _, made = KYCDocumentRequirement.objects.update_or_create(
                    organization=org, code=spec['code'],
                    defaults=spec,
                )
                if made:
                    created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  ✅ {created} new, {len(REQUIREMENTS) - created} already existed.'
            ))

        self.stdout.write(self.style.SUCCESS('\n🎉 KYC document requirements seeded.'))