# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# NOTE: TokenObtainPairView is intentionally NOT imported here —
# /api/auth/token/ is served by apps.core.urls → CustomTokenObtainPairView.
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.views_pages import page_detail, blog_list, blog_detail, contact_submit, platform_documentation
from apps.core.views_landing import landing_page
from apps.portal.views import PortalLoginView
from apps.origination.views import CustomerLoanViewSet

import apps.core.views_auth_ui
import apps.core.views_legal
# 1. ADD THESE IMPORTS
from rest_framework.routers import DefaultRouter
from apps.origination.views import CustomerLoanViewSet

# 2. DEFINE THE CUSTOMER ROUTER HERE
customer_router = DefaultRouter()
customer_router.register(r'customer/loans', CustomerLoanViewSet, basename='customer-loans')


# ── Django Admin customization ────────────────────────────────
admin.site.site_header = "Nimbus MFI Platform"
admin.site.site_title = "Nimbus Admin"
admin.site.index_title = "Platform Overview"


class PublicSpectacularAPIView(SpectacularAPIView):
    permission_classes = []
    authentication_classes = []


class PublicSpectacularSwaggerView(SpectacularSwaggerView):
    permission_classes = []
    authentication_classes = []


urlpatterns = [
    # ---- Marketing / Landing ----
    path('', landing_page, name='landing'),
    path('docs/', platform_documentation, name='platform-docs'),

    # ---- Django Admin ----
    path('admin/', admin.site.urls),

    # ---- JWT token endpoints ----
    # /api/auth/token/          → CustomTokenObtainPairView (via include('apps.core.urls') below)
    # /api/auth/token/refresh/  → TokenRefreshView          (via include('apps.core.urls') below)
    # /api/auth/refresh/        → TokenRefreshView          (stock, kept for legacy frontend callers)
    #
    # DO NOT re-add a stock TokenObtainPairView at /api/auth/token/ here —
    # Django resolves patterns top-to-bottom, so a mount here would shadow
    # the custom view and no session would be created at login.
    path('api/auth/refresh/', TokenRefreshView.as_view(),     name='token_refresh'),

    # ---- API ----
    path('api/auth/',          include('apps.core.urls')),
    path('api/clients/',       include('apps.clients.urls')),
    path('api/loans/',         include('apps.loans.urls')),
    path('api/payments/',      include('apps.payments.urls')),
    path('api/reports/',       include('apps.reports.urls')),
    path('api/accounting/',    include('apps.accounting.urls')),
    path('api/expenses/',      include('apps.expenses.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/restructures/',  include('apps.restructures.urls')),
    path('api/origination/',   include('apps.origination.urls')),
    path('api/kyc/',           include('apps.kyc.urls')),

    # ---- Mobile money API ----
    path('api/momo/', include('apps.momo.urls')),

    # ---- API Documentation ----
    path('api/schema/', PublicSpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',   PublicSpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ---- Legal pages (before pages/<slug> catch-all) ----
    path('pages/terms/',   apps.core.views_legal.terms_page,   name='ui-terms'),
    path('pages/privacy/', apps.core.views_legal.privacy_page, name='ui-privacy'),
    path('pages/sla/',     apps.core.views_legal.sla_page,     name='ui-sla'),

    # ---- CMS Pages & Blog ----
    path('pages/<slug:slug>/', page_detail, name='page-detail'),
    path('blog/',              blog_list,   name='blog-list'),
    path('blog/<slug:slug>/',  blog_detail, name='blog-detail'),
    path('contact/submit/',    contact_submit, name='contact-submit'),

    # ---- App UI pages (specific routes first) ----
    path('app/clients/<uuid:pk>/',   apps.core.views_auth_ui.client_detail_page,   name='ui-client-detail'),
    path('app/loans/<uuid:pk>/',     apps.core.views_auth_ui.loan_detail_page,     name='ui-loan-detail'),

    # Payments — /new/ must come before /<uuid>/
    path('app/payments/new/',        apps.core.views_auth_ui.payment_new_page,     name='ui-payment-new'),
    path('app/payments/field-approvals/',  apps.core.views_auth_ui.ui_field_approvals, name='ui-field-approvals'),

    path('app/payments/<uuid:pk>/',  apps.core.views_auth_ui.payment_detail_page,  name='ui-payment-detail'),

    # Dashboard / Reports / Expenses (specific routes)
    path('app/dashboard/executive/', apps.core.views_auth_ui.ui_executive_dashboard, name='ui-executive-dashboard'),
    path('app/reports/',             apps.core.views_auth_ui.ui_reports,             name='ui-reports'),

    path('app/expenses/',            apps.core.views_auth_ui.ui_expenses,            name='ui-expenses'),
    path('app/expenses/new/',        apps.core.views_auth_ui.ui_expense_new,         name='ui-expense-new'),
    path('app/expenses/<uuid:pk>/',  apps.core.views_auth_ui.ui_expense_detail,      name='ui-expense-detail'),

    # Settings & Admin (MUST be before the /app/ sub-includes so the specific
    # /app/settings/ route wins over any catch-all inside the includes)
    path('app/settings/',            apps.core.views_auth_ui.ui_settings,            name='ui-settings'),
    path('app/users/',               apps.core.views_auth_ui.ui_users,               name='ui-users'),
    path('app/users/<uuid:pk>/',     apps.core.views_auth_ui.ui_user_detail,         name='ui-user-detail'),
    path('app/branches/',            apps.core.views_auth_ui.ui_branches,            name='ui-branches'),
    path('app/branches/<uuid:pk>/',  apps.core.views_auth_ui.ui_branch_detail,       name='ui-branch-detail'),

    # ---- App sub-includes ----
    path('app/', include('apps.notifications.urls_pages')),
    path('app/', include('apps.origination.urls_pages')),
    path('app/', include('apps.loans.urls_pages')),
    path('app/', include('apps.restructures.urls_pages')),
    path('app/', include('apps.reports.urls_pages')),
    path('app/', include('apps.payments.urls_wallet_pages')),
    path('app/', include('apps.momo.urls_pages')),   # ← mobile money UI pages

    # ---- Client portal ----
    path('portal/', include('apps.portal.urls')),

    # ---- Auth UI pages ----
    path('pending-verification/',
         apps.core.views_auth_ui.pending_verification_page,
         name='ui-pending-verification'),

    path('sign-agreement/',
         apps.core.views_auth_ui.sign_agreement_page,
         name='ui-sign-agreement'),

    # POST handler for the agreement-signing form (requires apps/core/views_auth.py)
    path('auth/sign-agreement/',
         __import__('apps.core.views_auth', fromlist=['sign_agreement_view']).sign_agreement_view,
         name='auth-sign-agreement'),

    # ---- Auth UI pages catch-all (keep LAST) ----
    path('', include('apps.core.urls_auth')),
    #For customer login control to the Mobile App
    path('api/portal/login/', PortalLoginView.as_view(), name='api-portal-login'),
    path('api/', include(customer_router.urls)),
    #Payroll Module
    path('api/payroll/', include('apps.payroll.urls')),
    path('app/', include('apps.payroll.urls_pages')),
    
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)