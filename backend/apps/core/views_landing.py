from django.shortcuts import render
from .models import SiteSettings, LandingSection


def landing_page(request):
    """Public landing page rendered from admin-managed content."""
    site = SiteSettings.load()
    sections = (
        LandingSection.objects
        .filter(is_visible=True)
        .prefetch_related('items')
    )
    # Filter out items marked invisible
    for section in sections:
        section.visible_items = [i for i in section.items.all() if i.is_visible]

    context = {
        'site': site,
        'sections': sections,
    }
    return render(request, 'landing/index.html', context)