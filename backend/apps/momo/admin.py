# apps/momo/admin.py
from django.contrib import admin

from .models import MomoProviderConfig, PaymentIntent, DisbursementIntent


# Per-provider field help
PROVIDER_FIELD_LABELS = {
    'FAKE': {
        'api_key': '(not used)',
        'api_secret': '(not used)',
        'merchant_id': '(not used)',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': '(not used)',
        'webhook_secret': 'Any test string, e.g. "test-secret-123"',
    },
    'MTN_MOMO': {
        'api_key': 'API Key (32 chars, from MTN sandbox or merchant portal)',
        'api_secret': '(not used)',
        'merchant_id': 'API User UUID (from MTN sandbox provisioning)',
        'short_code': '(optional) Merchant short code',
        'subscription_key': 'Ocp-Apim-Subscription-Key (Collections product)',
        'callback_url': 'Public URL MTN calls back, e.g. https://…/api/momo/webhook/collection/MTN_MOMO/',
        'webhook_secret': '(not used — MTN posts unsigned callbacks)',
    },
    'AIRTEL_MONEY': {
        'api_key': 'Client ID (from Airtel Developer Portal)',
        'api_secret': 'Client Secret',
        'merchant_id': '(not used)',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': '(not used)',
        'webhook_secret': 'Set after signing webhook agreement',
    },
    'ZAMTEL': {
        'api_key': 'Bearer token / API key',
        'api_secret': '(not used)',
        'merchant_id': 'Zamtel merchant ID',
        'short_code': '(optional)',
        'subscription_key': '(not used)',
        'callback_url': 'API base URL, e.g. https://api.zamtel.co.zm/v1',
        'webhook_secret': 'Set after signing webhook agreement',
    },
    'KAZANG': {
        'api_key': 'Kazang API key',
        'api_secret': '(not used)',
        'merchant_id': '(not used)',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': 'Kazang API base URL',
        'webhook_secret': '(not used — redirect flow)',
    },
    'IZWE': {
        'api_key': 'IZwe API key',
        'api_secret': '(not used)',
        'merchant_id': 'IZwe merchant code',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': 'IZwe API base URL',
        'webhook_secret': 'Shared secret',
    },
    'BROADPAY': {
        'api_key': 'Lenco Bearer token',
        'api_secret': '(not used)',
        'merchant_id': '(not used)',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': '(not used)',
        'webhook_secret': 'Lenco webhook secret',
    },
    'ZYNLE': {
        'api_key': 'Zynle API ID',
        'api_secret': 'Zynle Private Key',
        'merchant_id': '(not used)',
        'short_code': '(not used)',
        'subscription_key': '(not used)',
        'callback_url': '(not used)',
        'webhook_secret': 'Zynle webhook signature',
    },
}


@admin.register(MomoProviderConfig)
class MomoProviderConfigAdmin(admin.ModelAdmin):
    list_display = [
        'organization', 'branch', 'provider_code',
        'is_active', 'is_sandbox', 'updated_at',
    ]
    list_filter = ['organization', 'branch', 'provider_code', 'is_active', 'is_sandbox']
    search_fields = [
        'organization__code', 'organization__name',
        'branch__code', 'branch__name',
        'merchant_id', 'short_code',
    ]
    autocomplete_fields = ['organization', 'branch']
    readonly_fields = ['id', 'created_at', 'updated_at']
    change_form_template = 'admin/momo/config_change_form.html'

    fieldsets = (
        ('Provider', {
            'fields': (
                'id', 'organization', 'branch', 'provider_code',
                'display_name', 'is_active', 'is_sandbox',
            ),
            'description': (
                'Leave Branch blank for an MFI-wide default wallet. '
                'Set a branch to make this the dedicated wallet for that '
                'branch — collections and disbursements from that branch '
                'will prefer it over the default.'
            ),
        }),
        ('API Credentials', {
            'fields': ('api_key', 'api_secret', 'merchant_id',
                       'short_code', 'subscription_key'),
            'description': 'See the docs for which fields this provider requires.',
        }),
        ('Endpoints & Webhooks', {
            'fields': ('callback_url', 'webhook_secret'),
        }),
        ('GL Accounts', {
            'fields': ('collection_gl_code', 'disbursement_gl_code'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context['field_labels'] = PROVIDER_FIELD_LABELS.get(obj.provider_code, {})
            extra_context['webhook_url'] = request.build_absolute_uri(
                f'/api/momo/webhook/collection/{obj.provider_code}/'
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('branch', 'organization')


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ['reference', 'provider_code', 'amount', 'phone', 'status', 'created_at']
    list_filter = ['provider_code', 'status', 'created_at']
    search_fields = ['reference', 'provider_txn_id', 'phone',
                     'client__first_name', 'client__last_name']
    readonly_fields = ['id', 'reference', 'provider_txn_id',
                       'raw_request', 'raw_response',
                       'created_at', 'confirmed_at']
    raw_id_fields = ['organization', 'branch', 'client', 'loan', 'payment']
    date_hierarchy = 'created_at'


@admin.register(DisbursementIntent)
class DisbursementIntentAdmin(admin.ModelAdmin):
    list_display = ['reference', 'provider_code', 'amount', 'phone', 'status',
                    'created_at', 'completed_at']
    list_filter = ['provider_code', 'status', 'created_at']
    search_fields = ['reference', 'provider_txn_id', 'phone',
                     'client__first_name', 'client__last_name']
    readonly_fields = ['id', 'reference', 'provider_txn_id',
                       'raw_request', 'raw_response',
                       'created_at', 'completed_at']
    raw_id_fields = ['organization', 'branch', 'client', 'loan', 'initiated_by']
    date_hierarchy = 'created_at'