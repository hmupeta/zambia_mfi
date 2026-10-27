# core/admin.py

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.utils import timezone

from .models import (
    # Tenancy & users
    Organization,
    OrganizationSettings,
    Branch,
    User,
    # Compliance
    LegalDocument,
    OrganizationAgreement,
    AuditLog,
    # CMS — Site settings & landing
    SiteSettings,
    LandingSection,
    SectionItem,
    # CMS — Pages & blog
    Page,
    ContentBlock,
    BlogPost,
    NavItem,
    ContactSubmission,
)


# ═══════════════════════════════════════════════════════════
# Organization
# ═══════════════════════════════════════════════════════════
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'subscription_tier', 'is_active',
        'boz_license_number_display', 'pacra_number_display', 'created_at',
    )
    list_filter = ('is_active', 'subscription_tier', 'created_at')
    search_fields = (
        'code', 'name', 'email',
        'settings__boz_license_number', 'settings__pacra_number',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    actions = ['verify_and_activate', 'suspend']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('settings')

    @admin.display(description='BoZ Licence')
    def boz_license_number_display(self, obj):
        return (
            getattr(obj.settings, 'boz_license_number', '—')
            if hasattr(obj, 'settings') else '—'
        )

    @admin.display(description='PACRA')
    def pacra_number_display(self, obj):
        return (
            getattr(obj.settings, 'pacra_number', '—')
            if hasattr(obj, 'settings') else '—'
        )

    @transaction.atomic
    def verify_and_activate(self, request, queryset):
        """
        Verify the BoZ licence and activate the tenant.
        The admin must have manually confirmed the licence number against the
        Bank of Zambia's public register BEFORE running this action.
        """
        activated = 0
        skipped = 0
        for org in queryset:
            if org.is_active:
                skipped += 1
                continue

            if not hasattr(org, 'settings') or not org.settings.boz_license_number:
                self.message_user(
                    request,
                    f"Cannot activate {org.code}: no BoZ licence on record.",
                    level=messages.ERROR,
                )
                continue

            org.is_active = True
            org.save(update_fields=['is_active', 'updated_at'])
            activated += 1

            AuditLog.objects.create(
                organization=org,
                user=request.user,
                action='ORGANIZATION_ACTIVATED',
                entity_type='Organization',
                entity_id=org.id,
                new_values={
                    'is_active': True,
                    'boz_license_number': org.settings.boz_license_number,
                    'verified_by': request.user.username,
                    'verified_at': timezone.now().isoformat(),
                },
                ip_address=request.META.get('REMOTE_ADDR'),
            )

        if activated:
            msg = f"{activated} organization(s) activated."
            if skipped:
                msg += f" {skipped} already active and skipped."
            self.message_user(request, msg, level=messages.SUCCESS)

    verify_and_activate.short_description = "Verify BoZ licence & activate selected tenants"

    @transaction.atomic
    def suspend(self, request, queryset):
        count = queryset.filter(is_active=True).update(is_active=False)
        for org in queryset.filter(is_active=False):
            AuditLog.objects.create(
                organization=org,
                user=request.user,
                action='ORGANIZATION_SUSPENDED',
                entity_type='Organization',
                entity_id=org.id,
                new_values={
                    'is_active': False,
                    'suspended_by': request.user.username,
                },
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        self.message_user(
            request,
            f"{count} organization(s) suspended.",
            level=messages.WARNING,
        )

    suspend.short_description = "Suspend selected tenants"


# ═══════════════════════════════════════════════════════════
# OrganizationSettings
# ═══════════════════════════════════════════════════════════
@admin.register(OrganizationSettings)
class OrganizationSettingsAdmin(admin.ModelAdmin):
    list_display = ('organization', 'boz_license_number', 'pacra_number', 'tin')
    search_fields = (
        'organization__name', 'organization__code',
        'boz_license_number', 'pacra_number', 'tin',
    )
    autocomplete_fields = ['organization']
    readonly_fields = ('updated_at',)

    fieldsets = (
        ('Organisation', {
            'fields': ('organization', 'legal_name', 'trading_name'),
        }),
        ('Regulatory', {
            'fields': ('boz_license_number', 'pacra_number', 'tin'),
        }),
        ('Contact', {
            'fields': ('physical_address', 'phone', 'email', 'website'),
        }),
        ('Branding', {
            'fields': ('logo', 'favicon', 'accent_color', 'primary_color'),
        }),
        ('Financial', {
            'fields': (
                'default_currency', 'fiscal_year_start_month',
                'default_interest_rate', 'default_penalty_rate',
                'default_grace_period_days',
            ),
        }),
        ('Operations', {
            'fields': (
                'loan_approval_threshold', 'expense_approval_threshold',
                'password_min_length', 'session_timeout_minutes', 'enable_2fa',
            ),
        }),
        ('Notifications', {
            'fields': (
                'sms_sender_id', 'sms_gateway_url', 'sms_gateway_api_key',
                'email_from_address',
            ),
        }),
    )


# ═══════════════════════════════════════════════════════════
# Branch
# ═══════════════════════════════════════════════════════════
@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'organization', 'is_hq', 'is_active', 'phone']
    list_filter = ['organization', 'is_hq', 'is_active']
    search_fields = ['code', 'name', 'physical_address']
    autocomplete_fields = ['organization', 'parent_branch']
    readonly_fields = ['id', 'created_at', 'updated_at']


# ═══════════════════════════════════════════════════════════
# User
# ═══════════════════════════════════════════════════════════
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'username', 'email', 'first_name', 'last_name',
        'role', 'organization', 'branch', 'is_active', 'is_platform_admin',
    ]
    list_filter = ['role', 'is_active', 'is_platform_admin', 'organization', 'branch']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    autocomplete_fields = ['organization', 'branch']
    ordering = ['username']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('MFI Info', {
            'fields': ('role', 'organization', 'branch', 'phone', 'is_platform_admin'),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('MFI Info', {
            'fields': ('email', 'role', 'organization', 'branch', 'phone', 'is_platform_admin'),
        }),
    )


# ═══════════════════════════════════════════════════════════
# Legal & Compliance
# ═══════════════════════════════════════════════════════════
@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'version', 'effective_date', 'is_active')
    list_filter = ('doc_type', 'is_active', 'effective_date')
    search_fields = ('title', 'version', 'content')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizationAgreement)
class OrganizationAgreementAdmin(admin.ModelAdmin):
    list_display = ('organization', 'document', 'status', 'signed_at', 'signed_by')
    list_filter = ('status', 'document__doc_type', 'signed_at')
    search_fields = (
        'organization__name', 'organization__code',
        'signed_by_name', 'signed_by_title',
    )
    autocomplete_fields = ['organization', 'document', 'signed_by']
    readonly_fields = (
        'id', 'signature_ip', 'user_agent',
        'signed_at', 'created_at', 'updated_at',
    )


# ═══════════════════════════════════════════════════════════
# Audit Log
# ═══════════════════════════════════════════════════════════
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'organization', 'user',
        'action', 'entity_type', 'entity_id', 'ip_address',
    ]
    list_filter = ['action', 'entity_type', 'organization']
    search_fields = ['user__username', 'entity_type', 'entity_id']
    readonly_fields = [
        'organization', 'user', 'branch', 'action', 'entity_type',
        'entity_id', 'old_values', 'new_values', 'ip_address', 'created_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ═══════════════════════════════════════════════════════════
# Site Settings (Singleton)
# ═══════════════════════════════════════════════════════════
@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Identity', {
            'fields': ('site_name', 'site_short_name', 'site_tagline', 'logo', 'favicon'),
        }),
        ('Branding', {
            'fields': ('primary_color', 'accent_color', 'background_color'),
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
        }),
        ('Contact', {
            'fields': ('contact_email', 'contact_phone', 'contact_address'),
        }),
        ('Social', {
            'fields': ('facebook_url', 'twitter_url', 'linkedin_url', 'instagram_url'),
        }),
        ('Navigation', {
            'fields': ('login_url', 'api_docs_url'),
        }),
        ('Footer', {
            'fields': ('footer_copyright', 'footer_note'),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# ═══════════════════════════════════════════════════════════
# Landing Sections
# ═══════════════════════════════════════════════════════════
class SectionItemInline(admin.TabularInline):
    model = SectionItem
    extra = 0
    fields = ['order', 'title', 'subtitle', 'icon', 'badge', 'is_visible']
    ordering = ['order']
    show_change_link = True


@admin.register(LandingSection)
class LandingSectionAdmin(admin.ModelAdmin):
    list_display = ['order', 'key', 'section_type', 'title', 'is_visible']
    list_display_links = ['key']
    list_editable = ['order', 'is_visible']
    list_filter = ['section_type', 'is_visible']
    search_fields = ['key', 'title', 'subtitle']
    inlines = [SectionItemInline]
    ordering = ['order', 'key']
    fieldsets = (
        ('Section', {
            'fields': ('key', 'section_type', 'anchor', 'order', 'is_visible', 'background'),
        }),
        ('Content', {
            'fields': ('eyebrow', 'title', 'subtitle'),
        }),
        ('Extras', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
    )


@admin.register(SectionItem)
class SectionItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'section', 'title', 'subtitle', 'is_visible']
    list_filter = ['section', 'is_visible']
    search_fields = ['title', 'subtitle', 'description']
    ordering = ['section', 'order']


# ═══════════════════════════════════════════════════════════
# Pages (CMS)
# ═══════════════════════════════════════════════════════════
class ContentBlockInline(admin.StackedInline):
    model = ContentBlock
    extra = 0
    fields = [
        ('order', 'block_type', 'is_visible'),
        ('title', 'subtitle'),
        'body',
        'image',
        ('cta_text', 'cta_url'),
        ('alignment', 'background'),
        'metadata',
    ]
    ordering = ['order']


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'template', 'is_published', 'order', 'updated_at']
    list_filter = ['template', 'is_published', 'show_in_header', 'show_in_footer']
    search_fields = ['title', 'slug', 'subtitle']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ContentBlockInline]
    list_editable = ['order', 'is_published']
    list_display_links = ['title']
    fieldsets = (
        ('Identity', {'fields': ('slug', 'title', 'subtitle')}),
        ('Layout', {'fields': ('template', 'hero_image')}),
        ('SEO', {'fields': ('meta_title', 'meta_description')}),
        ('Publishing', {
            'fields': ('is_published', 'order', 'show_in_header', 'show_in_footer'),
        }),
    )


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ['order', 'page', 'block_type', 'title', 'is_visible']
    list_filter = ['block_type', 'background', 'alignment', 'is_visible']
    search_fields = ['title', 'subtitle', 'body']
    list_editable = ['order', 'is_visible']
    list_display_links = ['title']
    ordering = ['page', 'order']


# ═══════════════════════════════════════════════════════════
# Blog
# ═══════════════════════════════════════════════════════════
@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'status', 'is_featured', 'published_at', 'views']
    list_filter = ['status', 'category', 'is_featured', 'author']
    search_fields = ['title', 'excerpt', 'body', 'tags']
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ['status', 'is_featured']
    list_display_links = ['title']
    date_hierarchy = 'published_at'
    fieldsets = (
        ('Identity', {'fields': ('slug', 'title', 'excerpt')}),
        ('Content', {'fields': ('body', 'cover_image')}),
        ('Classification', {'fields': ('category', 'tags', 'author')}),
        ('Publishing', {
            'fields': ('status', 'published_at', 'is_featured', 'views'),
        }),
        ('SEO', {'fields': ('meta_title', 'meta_description')}),
    )


# ═══════════════════════════════════════════════════════════
# Navigation
# ═══════════════════════════════════════════════════════════
@admin.register(NavItem)
class NavItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'menu', 'label', 'url', 'page', 'is_visible']
    list_filter = ['menu', 'is_visible']
    search_fields = ['label', 'url']
    list_editable = ['order', 'is_visible']
    list_display_links = ['label']
    autocomplete_fields = ['page']


# ═══════════════════════════════════════════════════════════
# Contact Submissions
# ═══════════════════════════════════════════════════════════
@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'name', 'email', 'subject', 'is_read']
    list_filter = ['is_read']
    search_fields = ['name', 'email', 'subject', 'message']
    readonly_fields = [
        'id', 'name', 'email', 'phone', 'company', 'subject',
        'message', 'ip_address', 'created_at',
    ]
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True