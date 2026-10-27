# apps/portal/models.py
import uuid
from django.db import models


class ClientPortalAccount(models.Model):
    """
    Client-facing login account. One per Client (1:1).
    Login identifier = client.phone (no separate username).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.OneToOneField(
        'clients.Client', on_delete=models.CASCADE,
        related_name='portal_account',
    )
    password = models.CharField(max_length=255, help_text='Hashed with Django password hashers.')
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # Brute-force protection
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_portal_accounts'

    def __str__(self):
        return f'Portal account — {self.client}'