from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Page, ContentBlock, BlogPost, NavItem


class Command(BaseCommand):
    help = 'Seed sample About, Contact pages and a blog post.'

    def handle(self, *args, **options):
        # --- About page ---
        about, _ = Page.objects.update_or_create(
            slug='about',
            defaults={
                'title': 'Built for Zambian microfinance',
                'subtitle': 'Nimbus Investment Ltd was founded to bring world-class lending infrastructure to MFIs across Zambia.',
                'template': 'about',
                'show_in_header': True,
                'show_in_footer': True,
                'order': 10,
            },
        )
        ContentBlock.objects.filter(page=about).delete()
        ContentBlock.objects.create(
            page=about, block_type='image_text', order=10,
            title='Our mission',
            body='We believe every Zambian business deserves access to fair, transparent credit.\n\nNimbus gives MFIs the tools to serve them at scale — with the accounting rigour that regulators demand and the speed that borrowers expect.',
            alignment='left',
        )
        ContentBlock.objects.create(
            page=about, block_type='stats', order=20,
            background='cream',
            metadata={'items': [
                {'value': '2026', 'label': 'Founded'},
                {'value': '15+', 'label': 'MFI modules'},
                {'value': '100+', 'label': 'REST endpoints'},
                {'value': '∞', 'label': 'Tenants supported'},
            ]},
        )
        ContentBlock.objects.create(
            page=about, block_type='grid', order=30,
            title='What drives us',
            subtitle='Four principles guide every decision.',
            metadata={'items': [
                {'icon': 'shield', 'title': 'Rigour', 'description': 'Every transaction is journalled. Every decision is auditable.'},
                {'icon': 'lightning', 'title': 'Speed', 'description': 'Loans disbursed in minutes, not weeks.'},
                {'icon': 'user-group', 'title': 'Partnership', 'description': 'We succeed when our MFIs succeed.'},
                {'icon': 'chart', 'title': 'Insight', 'description': 'Live dashboards that surface risk before it becomes a problem.'},
            ]},
        )

        # --- Contact page ---
        contact, _ = Page.objects.update_or_create(
            slug='contact',
            defaults={
                'title': 'Get in touch',
                'subtitle': 'Book a demo, ask a question, or just say hello.',
                'template': 'contact',
                'show_in_header': True,
                'show_in_footer': True,
                'order': 20,
            },
        )
        ContentBlock.objects.filter(page=contact).delete()
        ContentBlock.objects.create(
            page=contact, block_type='paragraph', order=10,
            title='We reply within one business day',
            body='Fill in the form and one of our specialists will reach out shortly.',
        )

        # --- Blog ---
        BlogPost.objects.update_or_create(
            slug='why-zambian-mfis-need-modern-software',
            defaults={
                'title': 'Why Zambian MFIs need modern lending software in 2026',
                'excerpt': 'The BFSA 2026 changed everything. Here is what MFIs need to know before the next regulatory inspection.',
                'body': (
                    '# The regulatory shift\n\n'
                    'With the Banking and Financial Services Act 2026 now in force, the old Money Lenders Act framework is gone. Every MFI must be licensed, capitalised, and reporting to the Bank of Zambia.\n\n'
                    '## What this means in practice\n\n'
                    '- **Strict capital requirements** — minimum capital, ongoing capital adequacy tests\n'
                    '- **Loan classification** — every loan must be classified by days past due\n'
                    '- **Provisioning** — mandatory provisions per the 2018 BoZ directives\n'
                    '- **Reporting** — monthly NPL schedules, quarterly prudential returns\n\n'
                    '## Why spreadsheets won\'t cut it\n\n'
                    'A spreadsheet cannot enforce double-entry accounting. It cannot compute loan loss provisions correctly. It cannot prove that a transaction wasn\'t altered after the fact.\n\n'
                    '## What to look for in a system\n\n'
                    '1. Real double-entry General Ledger\n'
                    '2. Automated BoZ prudential returns\n'
                    '3. Immutable audit trail\n'
                    '4. Multi-branch operations with consolidated reporting\n'
                    '5. Mobile money integration\n\n'
                    '> The MFIs that adopt modern software now will be the ones writing loans this time next year.'
                ),
                'category': 'Compliance',
                'tags': 'bank of zambia, compliance, bfsa',
                'status': 'published',
                'published_at': timezone.now(),
                'is_featured': True,
            },
        )

        # --- Nav ---
        NavItem.objects.filter(menu='header').delete()
        NavItem.objects.create(menu='header', label='About', page=about, order=10)
        NavItem.objects.create(menu='header', label='Blog', url='/blog/', order=20)
        NavItem.objects.create(menu='header', label='Contact', page=contact, order=30)

        self.stdout.write(self.style.SUCCESS('✅ Seeded About, Contact pages, 1 blog post, and 3 nav items.'))
        self.stdout.write('   Visit: /pages/about/  ·  /pages/contact/  ·  /blog/')