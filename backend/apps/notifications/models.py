import uuid
from django.db import models

from apps.core.models import Organization
from apps.clients.models import Client


CHANNEL_CHOICES = [
    ('SMS', 'SMS'),
    ('WHATSAPP', 'WhatsApp'),
    ('EMAIL', 'Email'),
]

STATUS_CHOICES = [
    ('QUEUED', 'Queued'),
    ('SENT', 'Sent'),
    ('DELIVERED', 'Delivered'),
    ('FAILED', 'Failed'),
]

PROVIDER_CHOICES = [
    ('AFRICAS_TALKING', "Africa's Talking"),
    ('TWILIO', 'Twilio'),
    ('META_CLOUD', 'Meta WhatsApp Cloud'),
    ('SMTP', 'SMTP'),
    ('SENDGRID', 'SendGrid'),
    ('NONE', 'None'),
]


class NotificationChannelConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='notification_config',
    )

    sms_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='AFRICAS_TALKING')
    sms_username = models.CharField(max_length=100, blank=True)
    sms_api_key = models.CharField(max_length=200, blank=True)
    sms_sender_id = models.CharField(max_length=20, blank=True)

    whatsapp_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='TWILIO')
    twilio_account_sid = models.CharField(max_length=100, blank=True)
    twilio_auth_token = models.CharField(max_length=200, blank=True)
    whatsapp_from = models.CharField(max_length=50, blank=True)

    email_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='SMTP')
    email_host = models.CharField(max_length=200, blank=True)
    email_port = models.PositiveIntegerField(default=587)
    email_username = models.CharField(max_length=200, blank=True)
    email_password = models.CharField(max_length=200, blank=True)
    email_use_tls = models.BooleanField(default=True)
    email_from_name = models.CharField(max_length=100, blank=True)
    email_from_address = models.CharField(max_length=200, blank=True)

    is_active = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)
    test_number = models.CharField(max_length=200, blank=True)
    default_country_code = models.CharField(max_length=5, default='260')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_channel_configs'

    def __str__(self):
        return f'Notification config - {self.organization.code}'


class NotificationTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='notification_templates',
    )
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=100)
    channel = models.CharField(
        max_length=20,
        choices=[
            ('SMS', 'SMS'),
            ('WHATSAPP', 'WhatsApp'),
            ('EMAIL', 'Email'),
            ('BOTH', 'SMS + WhatsApp'),
            ('ALL', 'All Channels'),
        ],
        default='SMS',
    )
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_templates'
        ordering = ['key']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'key'],
                name='unique_notification_template_key_per_org',
            ),
        ]

    def __str__(self):
        return f'{self.key} - {self.name}'


class NotificationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='notification_logs',
    )
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True,
    )
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications',
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    to_number = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')
    provider = models.CharField(max_length=30, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    sent_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications_sent',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['channel']),
        ]

    def __str__(self):
        return f'{self.channel} -> {self.to_number} [{self.status}]'
