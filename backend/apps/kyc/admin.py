from django.contrib import admin
from .models import (
    KYCDocumentRequirement, KYCVerification, KYCDocument, KYCCheck,
    KYCRiskAssessment, KYCReviewSchedule, KYCSelfServiceToken,
)


@admin.register(KYCDocumentRequirement)
class KYCDocumentRequirementAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'client_type', 'document_type', 'is_mandatory', 'is_active']
    list_filter = ['client_type', 'document_type', 'is_mandatory', 'is_active', 'organization']
    search_fields = ['code', 'name']
    autocomplete_fields = ['organization']


class KYCDocumentInline(admin.TabularInline):
    model = KYCDocument
    extra = 0
    readonly_fields = ['uploaded_at', 'extracted_data']


class KYCCheckInline(admin.TabularInline):
    model = KYCCheck
    extra = 0
    can_delete = False
    readonly_fields = ['check_type', 'result', 'provider', 'reference',
                       'confidence_score', 'checked_at']


@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ['verification_number', 'client', 'client_type', 'status',
                    'verified_at', 'expires_at']
    list_filter = ['status', 'client_type', 'organization']
    search_fields = ['verification_number', 'client__first_name', 'client__last_name']
    autocomplete_fields = ['organization', 'client', 'initiated_by', 'reviewed_by']
    readonly_fields = ['id', 'verification_number', 'initiated_at', 'submitted_at', 'verified_at']
    inlines = [KYCDocumentInline, KYCCheckInline]


@admin.register(KYCRiskAssessment)
class KYCRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ['verification', 'risk_level', 'risk_score',
                    'is_pep', 'is_sanctioned', 'requires_edd']
    list_filter = ['risk_level', 'is_pep', 'is_sanctioned', 'requires_edd']
    search_fields = ['verification__verification_number']
    autocomplete_fields = ['verification', 'assessed_by']


@admin.register(KYCReviewSchedule)
class KYCReviewScheduleAdmin(admin.ModelAdmin):
    list_display = ['client', 'risk_level', 'last_reviewed_at',
                    'next_review_due', 'is_active']
    list_filter = ['risk_level', 'is_active']
    search_fields = ['client__first_name', 'client__last_name']
    autocomplete_fields = ['client']


@admin.register(KYCSelfServiceToken)
class KYCSelfServiceTokenAdmin(admin.ModelAdmin):
    list_display = ['client', 'created_at', 'expires_at', 'is_used']
    list_filter = ['is_used']
    readonly_fields = ['token', 'created_at', 'used_at', 'ip_address']
    autocomplete_fields = ['client', 'created_by']