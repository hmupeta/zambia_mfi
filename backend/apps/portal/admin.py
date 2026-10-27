# apps/portal/admin.py
from django.contrib import admin
from django.contrib.auth.hashers import make_password

from .models import ClientPortalAccount


@admin.register(ClientPortalAccount)
class ClientPortalAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'is_active', 'last_login', 'failed_attempts', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'client__phone', 'client__nrc']
    autocomplete_fields = ['client']
    readonly_fields = ['id', 'password', 'last_login', 'failed_attempts', 'locked_until', 'created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        # Never let admin set plaintext password here
        super().save_model(request, obj, form, change)