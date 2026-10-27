from django.core.management.base import BaseCommand
from apps.core.models import SiteSettings, LandingSection, SectionItem


SECTIONS = [
    # ---------------------------------------------------------
    {
        'key': 'hero', 'section_type': 'hero', 'order': 10,
        'eyebrow': 'Bank of Zambia compliant · BFSA 2026 ready',
        'title': 'The lending platform your MFI deserves.',
        'subtitle': (
            'Multi-tenant, multi-branch loan management with full double-entry '
            'accounting, mobile money integration, and Bank of Zambia prudential '
            'reporting — all in one platform.'
        ),
        'background': 'cream',
        'metadata': {
            'primary_cta_text': 'Request a Demo',
            'primary_cta_url': '#contact',
            'secondary_cta_text': 'See Features',
            'secondary_cta_url': '#features',
        },
        'items': [
            {'title': 'MTN & Airtel Mobile Money', 'order': 10},
            {'title': 'IFRS-compliant General Ledger', 'order': 20},
            {'title': 'Multi-tenant by design', 'order': 30},
        ],
    },

    {
        'key': 'trust', 'section_type': 'trust', 'order': 20,
        'eyebrow': 'Built for the realities of Zambian lending',
        'title': '',
        'background': 'white',
        'items': [
            {'title': 'BFSA 2026', 'subtitle': 'Regulatory-ready', 'order': 10},
            {'title': 'ZMW', 'subtitle': 'Currency native', 'order': 20},
            {'title': 'IFRS 9', 'subtitle': 'ECL provisioning', 'order': 30},
            {'title': 'Multi-Tenant', 'subtitle': 'One platform, many MFIs', 'order': 40},
        ],
    },

    {
        'key': 'problem', 'section_type': 'problem', 'order': 30,
        'eyebrow': 'The Challenge',
        'title': 'Lending on spreadsheets is slow, risky, and unlicensed.',
        'subtitle': (
            'With the BFSA 2026 in force, unlicensed operations are a criminal offence. '
            'MFIs need a system that keeps them compliant, profitable, and audit-ready '
            'from day one.'
        ),
        'background': 'cream',
        'items': [
            {
                'title': 'Regulatory reporting on autopilot',
                'description': 'Generate NPL schedules, PAR ratios, and prudential returns directly from live General Ledger data.',
                'icon': 'chart', 'order': 10,
            },
            {
                'title': 'Get paid via mobile money',
                'description': 'Native MTN MoMo and Airtel Money integration. Repayments auto-allocate to principal, interest, and penalties.',
                'icon': 'phone', 'order': 20,
            },
            {
                'title': 'True double-entry accounting',
                'description': 'Every event posts a balanced journal entry. Trial Balance, P&L, and Balance Sheet ready 24/7.',
                'icon': 'shield', 'order': 30,
            },
        ],
    },

    {
        'key': 'features', 'section_type': 'features', 'order': 40,
        'eyebrow': 'Features',
        'title': "Everything an MFI needs. Nothing you don't.",
        'subtitle': 'Integrated modules that replace the spreadsheet, the ledger book, and the regulator\'s paperwork.',
        'anchor': 'features',
        'background': 'white',
        'items': [
            {'title': 'Multi-Tenant by Design', 'icon': 'building', 'order': 10,
             'description': 'Onboard multiple MFIs on one platform. Every tenant sees only their own branches, clients, and books.'},
            {'title': 'Multi-Branch Operations', 'icon': 'location', 'order': 20,
             'description': 'Model HQ, Regional, and Branch hierarchies. Each branch has its own wallet, portfolio, and reports.'},
            {'title': 'Mobile Money Native', 'icon': 'phone', 'order': 30,
             'description': 'MTN MoMo and Airtel Money for disbursements and collections. Automatic reconciliation and receipting.'},
            {'title': 'Full General Ledger', 'icon': 'document', 'order': 40,
             'description': 'ZICA-aligned chart of accounts. Automatic journal entries for every loan event.'},
            {'title': 'Bank Reconciliation', 'icon': 'clipboard', 'order': 50,
             'description': 'Import statements, auto-match against GL entries, reconcile to zero. Full audit trail.'},
            {'title': 'BoZ Prudential Returns', 'icon': 'chart', 'order': 60,
             'description': 'NPL schedule, PAR 1/7/30/60/90, and loan loss provisioning per the 2018 BoZ directives.'},
            {'title': 'SMS & WhatsApp Alerts', 'icon': 'chat', 'order': 70,
             'description': 'Automated reminders, payment confirmations, and overdue notices. Keep borrowers informed.'},
            {'title': 'Loan Restructuring', 'icon': 'refresh', 'order': 80,
             'description': 'Payment plans for struggling clients. Extend term, reduce amount, or grant moratoriums.'},
            {'title': 'Immutable Audit Trail', 'icon': 'shield', 'order': 90,
             'description': 'Every create, update, and delete is logged with who, what, when, and how.'},
        ],
    },

    {
        'key': 'how', 'section_type': 'how', 'order': 50,
        'eyebrow': 'How It Works',
        'title': 'From sign-up to first disbursement in under an hour.',
        'anchor': 'how',
        'background': 'cream',
        'items': [
            {'title': 'Onboard your MFI', 'order': 10,
             'description': 'A platform admin creates your tenant in seconds. Chart of Accounts, HQ branch, and first admin user are provisioned automatically.'},
            {'title': 'Configure products', 'order': 20,
             'description': 'Define loan products: amounts, tenures, interest methods, repayment frequencies. Set approval rules and user roles.'},
            {'title': 'Lend and grow', 'order': 30,
             'description': 'Register clients, approve loans, disburse via mobile money. Reports and regulatory filings update in real time.'},
        ],
    },

    {
        'key': 'stats', 'section_type': 'stats', 'order': 60,
        'title': '', 'background': 'dark',
        'items': [
            {'title': '10', 'subtitle': 'Integrated modules', 'order': 10},
            {'title': '100+', 'subtitle': 'REST endpoints', 'order': 20},
            {'title': '24/7', 'subtitle': 'Real-time reporting', 'order': 30},
            {'title': '∞', 'subtitle': 'Tenants supported', 'order': 40},
        ],
    },

    {
        'key': 'pricing', 'section_type': 'pricing', 'order': 70,
        'eyebrow': 'Pricing',
        'title': 'Simple, transparent, scalable.',
        'subtitle': 'Start free. Upgrade as your portfolio grows. No hidden fees.',
        'anchor': 'pricing',
        'background': 'white',
        'items': [
            {
                'title': 'Starter', 'subtitle': 'For new MFIs',
                'cta_text': 'Start Free Trial', 'cta_url': '#contact',
                'order': 10,
                'metadata': {
                    'price': 'K2,500', 'period': '/month',
                    'features': ['1 branch', 'Up to 5 users', '500 active loans', 'SMS notifications'],
                },
            },
            {
                'title': 'Professional', 'subtitle': 'For growing multi-branch MFIs',
                'badge': 'MOST POPULAR',
                'cta_text': 'Request a Demo', 'cta_url': '#contact',
                'order': 20,
                'metadata': {
                    'price': 'K7,500', 'period': '/month',
                    'features': ['Unlimited branches', 'Up to 25 users', 'Unlimited loans',
                                 'Mobile money integration', 'BoZ reporting', 'Priority support'],
                },
            },
            {
                'title': 'Enterprise', 'subtitle': 'For SACCOs, banks, and groups',
                'cta_text': 'Contact Sales', 'cta_url': '#contact',
                'order': 30,
                'metadata': {
                    'price': 'Custom', 'period': '',
                    'features': ['Unlimited everything', 'White-label branding',
                                 'Custom integrations', 'Dedicated infrastructure', 'SLA + training'],
                },
            },
        ],
    },

    {
        'key': 'faq', 'section_type': 'faq', 'order': 80,
        'eyebrow': 'FAQ',
        'title': "Questions? We've got answers.",
        'anchor': 'faq',
        'background': 'cream',
        'items': [
            {'title': 'Is Nimbus registered with the Bank of Zambia?', 'order': 10,
             'description': 'Nimbus Investment Ltd is the platform provider. The MFIs using our system are the licensed lenders. We ensure the platform meets all Bank of Zambia reporting requirements under the BFSA 2026.'},
            {'title': 'How does mobile money integration work?', 'order': 20,
             'description': 'We integrate directly with MTN Mobile Money and Airtel Money via their official APIs. Disbursements go out to the borrower, repayments reconcile automatically.'},
            {'title': 'Can I run multiple MFIs on the same installation?', 'order': 30,
             'description': 'Yes. Nimbus is multi-tenant by design. One installation can host unlimited MFIs, each with their own data. Isolation is enforced at the database level.'},
            {'title': 'What reports do I get for Bank of Zambia compliance?', 'order': 40,
             'description': 'NPL schedule, Portfolio at Risk (PAR 1, 7, 30, 60, 90), and loan loss provisioning — all generated live from the General Ledger.'},
            {'title': 'How long does implementation take?', 'order': 50,
             'description': 'A single-branch MFI can be up in under an hour. Multi-branch operations with mobile money integration typically take 1–2 weeks.'},
        ],
    },

    {
        'key': 'cta', 'section_type': 'cta', 'order': 90,
        'title': 'Ready to modernize your lending?',
        'subtitle': 'Book a 30-minute demo. See how Nimbus handles loans, mobile money, General Ledger, and BoZ reporting in one platform.',
        'anchor': 'contact',
        'background': 'dark',
        'metadata': {
            'primary_cta_text': 'Request a Demo',
            'primary_cta_url': 'mailto:hello@nimbus.zm',
            'secondary_cta_text': 'Call +260 211 000 000',
            'secondary_cta_url': 'tel:+260211000000',
            'email': 'hello@nimbus.zm',
        },
    },
]


class Command(BaseCommand):
    help = 'Seed the landing page with default content (idempotent).'

    def handle(self, *args, **options):
        # -- Site settings --
        site = SiteSettings.load()
        if not site.site_name or site.site_name == 'Nimbus Investment Ltd':
            self.stdout.write('  Site settings initialised.')
        self.stdout.write(self.style.SUCCESS('✅ Site settings ready.'))

        # -- Sections --
        created_sections = 0
        created_items = 0

        for spec in SECTIONS:
            items = spec.pop('items', [])
            key = spec['key']

            section, created = LandingSection.objects.update_or_create(
                key=key,
                defaults=spec,
            )
            if created:
                created_sections += 1

            for i_spec in items:
                # Match by (section, title) so updates don't duplicate
                title = i_spec.get('title', '')
                obj, i_created = SectionItem.objects.update_or_create(
                    section=section,
                    title=title,
                    defaults=i_spec,
                )
                if i_created:
                    created_items += 1

            # Restore spec for next loop if re-run (not required, but safe)
            spec['items'] = items

        self.stdout.write(self.style.SUCCESS(
            f'✅ Seeded {created_sections} new sections, {created_items} new items.'
        ))
        self.stdout.write(self.style.SUCCESS(
            '🎉 Landing page content is now editable at /admin/core/landingsection/'
        ))