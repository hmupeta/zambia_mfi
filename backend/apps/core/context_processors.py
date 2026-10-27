# apps/core/context_processors.py
"""
Template context processors.

Injects a `site` dict into every rendered template so templates can read
branding and organisation settings without a per-view query.

Registered in config/settings.py under TEMPLATES[0]['OPTIONS']['context_processors'].
"""

DEFAULTS = {
    'legal_name': 'Nimbus MFI',
    'trading_name': 'Nimbus',
    'tin': '',
    'pacra_number': '',
    'boz_license_number': '',
    'physical_address': '',
    'phone': '',
    'email': '',
    'website': '',
    'logo': None,
    'favicon': None,
    'accent_color': '#B45309',
    'primary_color': '#0A0A0A',
    'default_currency': 'ZMW',
}


def site_settings(request):
    """
    Returns {'site': {...}} for every request.

    Safe for anonymous users — falls back to DEFAULTS.
    If the user has an organization and it has an OrganizationSettings
    row, those values override the defaults.
    """
    site = dict(DEFAULTS)

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'site': site}

    org = getattr(user, 'organization', None)
    if not org:
        return {'site': site}

    # Import inside the function to avoid app-loading circular issues
    try:
        from .models import OrganizationSettings
    except Exception:
        return {'site': site}

    settings_obj = OrganizationSettings.objects.filter(organization=org).first()
    if not settings_obj:
        return {'site': site}

    for field in DEFAULTS.keys():
        value = getattr(settings_obj, field, None)
        if value not in (None, ''):
            site[field] = value

    return {'site': site}