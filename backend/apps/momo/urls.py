# apps/momo/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import webhooks, views_portal
from .views_admin import (
    PaymentIntentViewSet, DisbursementIntentViewSet,
    MomoConfigViewSet, provision_mtn_sandbox,
)

router = DefaultRouter()
router.register(r'intents/payments',      PaymentIntentViewSet,     basename='momo-payment-intent')
router.register(r'intents/disbursements', DisbursementIntentViewSet, basename='momo-disbursement-intent')
router.register(r'configs',               MomoConfigViewSet,        basename='momo-config')

urlpatterns = [
    # Sandbox provisioning
    path('provision-mtn-sandbox/', provision_mtn_sandbox, name='momo-provision-mtn-sandbox'),

    # Webhook receivers
    path('webhook/collection/<str:provider_code>/', webhooks.collection_webhook, name='momo-collection-webhook'),
    path('webhook/disbursement/<str:provider_code>/', webhooks.disbursement_webhook, name='momo-disbursement-webhook'),

    # Client portal endpoints (Legacy)
    path('portal/providers/', views_portal.list_providers, name='momo-portal-providers'),
    path('portal/pay/', views_portal.create_payment, name='momo-portal-pay'),
    path('portal/intent/<str:reference>/', views_portal.intent_status, name='momo-portal-intent-status'),

    # Client portal endpoints (MTN Request to Pay)
    path('portal/mtn-pay/', views_portal.mtn_request_to_pay, name='momo-portal-mtn-pay'),
    path('portal/mtn-status/<str:reference_id>/', views_portal.mtn_check_status, name='momo-portal-mtn-status'),

    # Everything else
    path('', include(router.urls)),
]