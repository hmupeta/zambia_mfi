from django.contrib import admin
from .models import NotificationChannelConfig, NotificationTemplate, NotificationLog


@admin.register(NotificationChannelConfig)
class NotificationChannelConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'sms_provider', 'whatsapp_provider', 'email_provider', 'is_active', 'is_sandbox']
    list_filter = ['is_active', 'is_sandbox']
    search_fields = ['organization__code']


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'channel', 'is_active', 'organization']
    list_filter = ['channel', 'is_active']
    search_fields = ['key', 'name', 'body', 'subject']


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'channel', 'to_number', 'client', 'status', 'provider']
    list_filter = ['channel', 'status', 'provider']
    search_fields = ['to_number', 'body']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at', 'sent_at', 'context']
