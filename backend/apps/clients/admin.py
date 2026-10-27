from django.contrib import admin
from .models import Client, ClientPaymentChannel, Guarantor, ClientDocument


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = [
        'nrc', 'first_name', 'last_name', 'phone',
        'organization', 'branch', 'kyc_status', 'is_active',
    ]
    list_filter = ['organization', 'branch', 'kyc_status', 'is_active', 'province', 'gender']
    search_fields = ['first_name', 'last_name', 'nrc', 'phone', 'email']
    autocomplete_fields = ['organization', 'branch', 'created_by']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Identity', {
            'fields': ('id', 'organization', 'branch', 'nrc',
                       'first_name', 'last_name', 'gender', 'date_of_birth', 'marital_status')
        }),
        ('Contact', {
            'fields': ('phone', 'alt_phone', 'email',
                       'home_address', 'village_or_area', 'district', 'province')
        }),
        ('Employment', {
            'fields': ('occupation', 'employer_name', 'employer_address')
        }),
        ('KYC', {
            'fields': ('photo', 'national_id_front', 'national_id_back', 'kyc_status', 'credit_score')
        }),
        ('Meta', {
            'fields': ('is_active', 'created_by', 'created_at', 'updated_at', 'deleted_at')
        }),
    )


@admin.register(ClientPaymentChannel)
class ClientPaymentChannelAdmin(admin.ModelAdmin):
    list_display = ['client', 'channel_type', 'account_number', 'is_default', 'is_verified']
    list_filter = ['channel_type', 'is_default', 'is_verified']
    search_fields = ['account_number', 'account_name', 'client__first_name', 'client__last_name']
    autocomplete_fields = ['client']


@admin.register(Guarantor)
class GuarantorAdmin(admin.ModelAdmin):
    list_display = ['name', 'client', 'relationship', 'phone', 'monthly_income']
    search_fields = ['name', 'phone', 'nrc', 'client__first_name', 'client__last_name']
    autocomplete_fields = ['client']


@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    list_display = ['client', 'document_type', 'uploaded_by', 'uploaded_at']
    list_filter = ['document_type']
    search_fields = ['client__first_name', 'client__last_name', 'client__nrc']
    autocomplete_fields = ['client', 'uploaded_by']
    readonly_fields = ['uploaded_at']