# apps/portal/views.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

# --- ADDED IMPORTS FOR THE CUSTOMER APP API ---
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import ClientPortalAccount
# ----------------------------------------------

from apps.loans.models import Loan, LoanProduct
from apps.payments.models import Payment
from apps.origination.models import LoanApplication
from apps.origination.services import ApplicationNumberService

from .auth import (
    authenticate_portal, log_in, log_out, get_current_client,
    portal_login_required, set_password, create_account_for_client,
)
from .forms import PortalLoginForm, PortalApplicationForm


# ============================================================
# Helper: resolve the org system user
# ============================================================
def _get_system_user(org):
    User = get_user_model()
    username = f'system@{org.code}'
    user = User.objects.filter(username=username).first()
    if user:
        return user
    user = User(
        username=username,
        first_name='System',
        last_name=f'Auto ({org.code})',
        role='HQ_ADMIN',
        is_active=True,
        is_staff=False,
    )
    if hasattr(user, 'organization_id'):
        user.organization = org
    user.set_unusable_password()
    user.save()
    return user


# ============================================================
# Login / Logout (WEB PORTAL)
# ============================================================
@require_http_methods(['GET', 'POST'])
def portal_login(request):
    if get_current_client(request):
        return redirect('portal-dashboard')

    form = PortalLoginForm(request.POST or None)
    error = None

    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        password = form.cleaned_data['password']
        client, account, err = authenticate_portal(phone, password)
        if client:
            log_in(request, client)
            next_url = request.GET.get('next') or reverse('portal-dashboard')
            return redirect(next_url)
        error = err

    return render(request, 'portal/login.html', {'form': form, 'error': error})


def portal_logout(request):
    log_out(request)
    return redirect('portal-login')


# ============================================================
# Dashboard
# ============================================================
@portal_login_required
def dashboard(request):
    client = request.portal_client
    today = timezone.now().date()

    active_loans = Loan.objects.filter(
        client=client, is_fully_repaid=False,
    ).order_by('-created_at')

    next_installments = []
    for loan in active_loans:
        inst = loan.installments.filter(is_paid=False).order_by('due_date').first()
        if inst:
            next_installments.append({'loan': loan, 'installment': inst})

    next_installments.sort(key=lambda x: x['installment'].due_date)

    total_outstanding = sum((l.balance_due or Decimal('0')) for l in active_loans)

    recent_payments = Payment.objects.filter(
        client=client, is_reversed=False,
    ).order_by('-received_at')[:5]

    return render(request, 'portal/dashboard.html', {
        'client': client,
        'active_loans': active_loans,
        'next_installments': next_installments[:3],
        'total_outstanding': total_outstanding,
        'recent_payments': recent_payments,
    })


# ============================================================
# Loans
# ============================================================
@portal_login_required
def loans_list(request):
    client = request.portal_client
    loans = Loan.objects.filter(client=client).order_by('-created_at')

    return render(request, 'portal/loans_list.html', {
        'client': client,
        'loans': loans,
    })


@portal_login_required
def loan_detail(request, pk):
    client = request.portal_client
    loan = get_object_or_404(Loan, id=pk, client=client)

    schedule = loan.installments.order_by('installment_no')
    payments = loan.payments.filter(is_reversed=False).order_by('-received_at')

    return render(request, 'portal/loan_detail.html', {
        'client': client,
        'loan': loan,
        'schedule': schedule,
        'payments': payments,
    })


# ============================================================
# New Application
# ============================================================
@portal_login_required
def apply_new(request):
    client = request.portal_client

    products = LoanProduct.objects.filter(
        organization=client.organization, is_active=True,
    ).order_by('code')

    error = None

    if request.method == 'POST':
        form = PortalApplicationForm(request.POST)
        form.fields['loan_product'].widget.choices = [
            (str(p.id), f'{p.code} — {p.name}') for p in products
        ]

        if form.is_valid():
            application = None
            try:
                product = LoanProduct.objects.get(
                    id=form.cleaned_data['loan_product'],
                    organization=client.organization,
                    is_active=True,
                )

                branch = client.branch
                if not branch:
                    error = (
                        'Your account is not yet assigned to a branch. '
                        'Please contact your branch to complete onboarding.'
                    )
                    raise ValueError(error)

                system_user = _get_system_user(client.organization)

                application = LoanApplication.objects.create(
                    organization=client.organization,
                    branch=branch,
                    client=client,
                    loan_product=product,
                    application_number=ApplicationNumberService.generate(
                        client.organization
                    ),
                    requested_amount=form.cleaned_data['amount'],
                    requested_tenure_months=form.cleaned_data['term_months'],
                    requested_repayment_frequency=product.repayment_frequency,
                    purpose=form.cleaned_data['purpose'],
                    purpose_notes=form.cleaned_data.get('purpose_notes', ''),
                    status='DRAFT',
                    created_by=system_user,
                )

                from apps.origination.services import ApplicationService

                try:
                    ApplicationService.submit(application, user=system_user)
                except TypeError:
                    ApplicationService.submit(application, system_user)

                application.refresh_from_db()

                if application.status != 'SUBMITTED':
                    raise RuntimeError(
                        f'Workflow did not submit the application '
                        f'(status still {application.status}).'
                    )

                messages.success(
                    request,
                    f'Application {application.application_number} submitted. '
                    f'We will contact you shortly.'
                )
                return redirect('portal-dashboard')

            except Exception as e:
                if application and application.pk:
                    try:
                        application.delete()
                    except Exception:
                        pass
                error = f'Could not submit application: {e}'
    else:
        form = PortalApplicationForm()
        form.fields['loan_product'].widget.choices = [
            (str(p.id), f'{p.code} — {p.name}') for p in products
        ]

    return render(request, 'portal/apply.html', {
        'client': client,
        'form': form,
        'products': products,
        'error': error,
    })


# ============================================================
# Profile
# ============================================================
@portal_login_required
def profile(request):
    client = request.portal_client
    success = None
    error = None

    if request.method == 'POST':
        old = request.POST.get('old_password', '')
        new1 = request.POST.get('new_password', '')
        new2 = request.POST.get('new_password2', '')

        if not old or not new1 or not new2:
            error = 'All password fields are required.'
        elif new1 != new2:
            error = 'New passwords do not match.'
        elif len(new1) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            from .auth import authenticate_portal
            _, account, err = authenticate_portal(client.phone, old)
            if err:
                error = 'Current password is incorrect.'
            else:
                set_password(account, new1)
                success = 'Password changed successfully.'

    return render(request, 'portal/profile.html', {
        'client': client,
        'success': success,
        'error': error,
    })

# ============================================================
# Applications (client-facing)
# ============================================================
@portal_login_required
def applications_list(request):
    client = request.portal_client

    applications = (
        LoanApplication.objects
        .filter(client=client, organization=client.organization)
        .select_related('loan_product', 'branch')
        .order_by('-created_at')
    )

    rows = []
    for app in applications:
        rows.append({
            'application': app,
            'status_label': _portal_status_label(app.status),
            'status_tone': _portal_status_tone(app.status),
        })

    return render(request, 'portal/applications_list.html', {
        'client': client,
        'rows': rows,
    })


@portal_login_required
def application_detail(request, pk):
    client = request.portal_client

    application = get_object_or_404(
        LoanApplication.objects.select_related('loan_product', 'branch'),
        id=pk,
        client=client,
        organization=client.organization,
    )

    return render(request, 'portal/application_detail.html', {
        'client': client,
        'application': application,
        'status_label': _portal_status_label(application.status),
        'status_tone': _portal_status_tone(application.status),
    })


# ------------------------------------------------------------
# Status label / tone helpers
# ------------------------------------------------------------
_PORTAL_STATUS_MAP = {
    'DRAFT':       ('Draft',                  'neutral'),
    'SUBMITTED':   ('Submitted',              'info'),
    'UNDER_REVIEW': ('Under review',           'info'),
    'APPROVED':    ('Approved',               'success'),
    'DISBURSED':   ('Disbursed',              'success'),
    'REJECTED':    ('Not approved',           'danger'),
    'DECLINED':    ('Not approved',           'danger'),
    'WITHDRAWN':   ('Withdrawn',              'neutral'),
    'CANCELLED':   ('Cancelled',              'neutral'),
}


def _portal_status_label(status):
    return _PORTAL_STATUS_MAP.get(status, (status.title() if status else '—', 'neutral'))[0]


def _portal_status_tone(status):
    return _PORTAL_STATUS_MAP.get(status, ('—', 'neutral'))[1]


# ============================================================
# MOBILE API (Customer App)
# ============================================================

class PortalLoginView(APIView):
    """
    API endpoint for the Flutter Customer App. 
    Strictly uses the Client's Phone Number for authentication.
    """
    permission_classes = [] 
    authentication_classes = [] # Prevents old tokens from blocking login

    def post(self, request):
        raw_phone = request.data.get('phone', '').strip()
        password = request.data.get('password')

        if not raw_phone or not password:
            return Response({'error': 'Phone and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- NORMALIZE PHONE NUMBER ---
        variations = [raw_phone]
        clean = raw_phone.replace(" ", "").replace("-", "")
        
        if clean.startswith("+260"):
            local = "0" + clean[4:]
            intl = clean[1:]
            variations.extend([local, intl])
        elif clean.startswith("260"):
            local = "0" + clean[3:]
            intl_plus = "+" + clean
            variations.extend([local, intl_plus])
        elif clean.startswith("0"):
            intl = "260" + clean[1:]
            intl_plus = "+260" + clean[1:]
            variations.extend([intl, intl_plus])

        try:
            account = ClientPortalAccount.objects.select_related('client').filter(
                client__phone__in=variations
            ).first()
            
            if not account:
                raise ClientPortalAccount.DoesNotExist
                
        except ClientPortalAccount.DoesNotExist:
            return Response({'error': 'Invalid phone or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not account.is_active:
            return Response({'error': 'This account is disabled. Contact your branch.'}, status=status.HTTP_403_FORBIDDEN)

        if not check_password(password, account.password):
            return Response({'error': 'Invalid phone or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username=f"client_{account.client.id}@{account.client.organization.code}",
            defaults={
                'organization': account.client.organization,
                'branch': account.client.branch,
                'role': 'TELLER', 
                'is_active': True,
            }
        )

        refresh = RefreshToken.for_user(user)
        refresh['client_id'] = str(account.client.id)
        refresh.access_token['client_id'] = str(account.client.id)

        account.last_login = timezone.now()
        account.save()

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })