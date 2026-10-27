# apps/momo/views_pages.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def mobile_money_settings_page(request):
    """
    Renders the HQ Admin's Mobile Money settings page.
    All data is fetched client-side from /api/momo/configs/.
    """
    return render(request, 'app/settings/mobile_money.html', {
        'breadcrumbs': [
            {'label': 'Admin',        'href': None},
            {'label': 'Settings',     'href': '/app/settings/'},
            {'label': 'Mobile Money', 'href': None},
        ],
    })