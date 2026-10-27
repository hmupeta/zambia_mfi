# core/views_legal.py

from django.shortcuts import render
from django.utils import timezone

from .models import LegalDocument


def _active_document(doc_type):
    """
    Fetch the currently-active document of a given type.
    Returns None if no active document exists — the template then falls back
    to inline static content.
    """
    today = timezone.now().date()
    return (
        LegalDocument.objects
        .filter(doc_type=doc_type, is_active=True, effective_date__lte=today)
        .order_by('-effective_date')
        .first()
    )


def terms_page(request):
    return render(request, 'legal/terms.html', {
        'document': _active_document('TERMS'),
        'page': 'terms',
    })


def privacy_page(request):
    return render(request, 'legal/privacy.html', {
        'document': _active_document('DPA'),
        'page': 'privacy',
    })


def sla_page(request):
    return render(request, 'legal/sla.html', {
        'document': _active_document('SLA'),
        'page': 'sla',
    })