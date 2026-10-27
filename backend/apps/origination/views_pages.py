# apps/origination/views_pages.py
from django.shortcuts import render


def applications_list(request):
    """Serve the Alpine.js applications list page."""
    return render(request, 'app/applications/list.html')


def application_new(request):
    """Serve the multi-step new application form."""
    return render(request, 'app/applications/new.html')


def application_detail(request, pk):
    """Serve the Alpine.js detail page — data fetched via API."""
    return render(request, 'app/applications/detail.html', {
        'application_id': str(pk),
    })