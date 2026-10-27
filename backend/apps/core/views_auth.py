# core/views_auth.py

from django.contrib.auth import authenticate, login as django_login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    LegalDocument, OrganizationAgreement, AuditLog,
)


@require_POST
def login_view(request):
    """
    Session-based login. Blocks users whose Organization is inactive
    (pending BoZ licence verification) or has been suspended.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    user = authenticate(request, username=username, password=password)

    if user is None:
        return redirect(f"{reverse('ui-login')}?error=invalid")

    # Platform admins bypass org checks
    if not user.is_platform_admin and user.organization_id:
        org = user.organization
        if not org.is_active:
            return redirect(f"{reverse('ui-login')}?error=org_inactive")

    django_login(request, user)

    # If the org still has unsigned active legal documents, force signing
    if not user.is_platform_admin and user.organization_id:
        active_doc_ids = set(
            LegalDocument.objects.filter(is_active=True)
            .values_list('id', flat=True)
        )
        signed_doc_ids = set(
            OrganizationAgreement.objects.filter(
                organization=user.organization, status='SIGNED'
            ).values_list('document_id', flat=True)
        )
        if active_doc_ids - signed_doc_ids:
            return redirect('ui-sign-agreement')

    return redirect('ui-dashboard')


@login_required
@require_POST
def sign_agreement_view(request):
    """
    Handles the POST from auth/sign_agreement.html.
    Records an OrganizationAgreement for each currently-unsigned active doc.
    """
    org = getattr(request.user, 'organization', None)
    if not org:
        return redirect('ui-dashboard')

    signed_by_name = request.POST.get('signed_by_name', '').strip()
    signed_by_title = request.POST.get('signed_by_title', '').strip()
    agreed = request.POST.get('agreed_to_terms')

    if not (signed_by_name and signed_by_title and agreed):
        return render(request, 'auth/sign_agreement.html', {
            'page': 'sign_agreement',
            'error': 'You must provide your name, title, and agree to the documents.',
            'documents': LegalDocument.objects.filter(is_active=True),
            'organization': org,
            'default_signed_by_name': signed_by_name,
        })

    active_docs = LegalDocument.objects.filter(is_active=True)
    signed_doc_ids = OrganizationAgreement.objects.filter(
        organization=org, status='SIGNED'
    ).values_list('document_id', flat=True)
    missing_docs = active_docs.exclude(id__in=signed_doc_ids)

    ip = request.META.get('REMOTE_ADDR')
    ua = request.META.get('HTTP_USER_AGENT', '')

    signed_types = []
    for doc in missing_docs:
        OrganizationAgreement.objects.update_or_create(
            organization=org,
            document=doc,
            defaults={
                'signed_by': request.user,
                'signed_by_name': signed_by_name,
                'signed_by_title': signed_by_title,
                'signature_ip': ip,
                'user_agent': ua,
                'signed_at': timezone.now(),
                'status': 'SIGNED',
            },
        )
        signed_types.append(f"{doc.doc_type} v{doc.version}")

    AuditLog.objects.create(
        organization=org,
        user=request.user,
        action='SIGN_AGREEMENT',
        entity_type='OrganizationAgreement',
        new_values={
            'signed_documents': signed_types,
            'signed_by_name': signed_by_name,
            'signed_by_title': signed_by_title,
        },
        ip_address=ip,
    )

    return redirect('ui-dashboard')


@login_required
def logout_view(request):
    from django.contrib.auth import logout as django_logout
    django_logout(request)
    return redirect('ui-login')