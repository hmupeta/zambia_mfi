# apps/momo/models.py
import uuid

from django.db import models
from django.utils import timezone
from apps.core.crypto import encrypt, decrypt


PROVIDER_CHOICES = [
    ('FAKE',         'Fake (Testing)'),
    ('MTN_MOMO',     'MTN Mobile Money'),
    ('AIRTEL_MONEY', 'Airtel Money'),
    ('ZAMTEL',       'Zamtel Money'),
    ('KAZANG',       'Kazang'),
    ('IZWE',         'IZwe Pay'),
    ('BROADPAY',     'Broadpay (Lenco)'),
    ('ZYNLE',        'Zynle Pay'),
]

TRANSACTION_TYPE_CHOICES = [
    ('COLLECTION',   'Collection (Receive Money)'),
    ('DISBURSEMENT', 'Disbursement (Send Money)'),
]

PAYMENT_INTENT_STATUS = [
    ('PENDING', 'Pending'),
    ('CONFIRMED', 'Confirmed'),
    ('FAILED', 'Failed'),
    ('EXPIRED', 'Expired'),
    ('CANCELLED', 'Cancelled'),
]

DISBURSEMENT_INTENT_STATUS = [
    ('PENDING', 'Pending'),
    ('PROCESSING', 'Processing'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
    ('CANCELLED', 'Cancelled'),
]


class MomoProviderConfig(models.Model):
    """Per-organization credentials for a mobile money provider."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='momo_configs',
    )
    branch = models.ForeignKey(
        'core.Branch', on_delete=models.CASCADE,
        related_name='momo_configs',
        null=True, blank=True,
        help_text=(
            'Leave blank for an MFI-wide default wallet. '
            'Set for a branch-specific wallet.'
        ),
    )
    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    
    # NEW FIELD: Distinguish between Collection and Disbursement
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        default='COLLECTION',
        help_text="Is this config for receiving payments or sending loans?"
    )
    
    display_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)

    # API credentials (structure varies by provider)
    api_key = models.CharField(
        max_length=500, blank=True,
        help_text='MTN: API Key. Airtel: client_id. Others: as documented.',
    )
    api_secret = models.CharField(
        max_length=500, blank=True,
        help_text='Airtel: client_secret. Leave blank for MTN.',
    )
    merchant_id = models.CharField(max_length=200, blank=True)
    short_code = models.CharField(max_length=50, blank=True)
    subscription_key = models.CharField(max_length=500, blank=True)

    # Webhook / callback
    webhook_secret = models.CharField(max_length=500, blank=True)
    callback_url = models.URLField(blank=True)

    # GL account codes used by this provider
    collection_gl_code = models.CharField(
        max_length=10, default='1030',
        help_text='GL code for inbound collections (Debit).',
    )
    disbursement_gl_code = models.CharField(
        max_length=10, default='1030',
        help_text='GL code for outbound payouts (Credit).',
    )

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'momo_provider_configs'
        constraints = [
            # One default (branch=NULL) per (org, provider, transaction_type)
            models.UniqueConstraint(
                fields=['organization', 'provider_code', 'transaction_type'],
                condition=models.Q(branch__isnull=True),
                name='unique_momo_provider_default_per_org',
            ),
            # One per (org, branch, provider, transaction_type) when branch is set
            models.UniqueConstraint(
                fields=['organization', 'branch', 'provider_code', 'transaction_type'],
                condition=models.Q(branch__isnull=False),
                name='unique_momo_provider_per_org_branch',
            ),
        ]

    def __str__(self):
        # Updated to show the type so you can tell them apart in Admin
        return f'{self.organization.code} - {self.provider_code} ({self.transaction_type})'

    def save(self, *args, **kwargs):
        secret_fields = ('api_key', 'api_secret', 'subscription_key', 'webhook_secret')
        for field in secret_fields:
            value = getattr(self, field)
            if value and not value.startswith('gAAAA'):
                setattr(self, field, encrypt(value))
        super().save(*args, **kwargs)

    def plain_credential(self, field):
        """Return the decrypted value of a secret field."""
        secret_fields = ('api_key', 'api_secret', 'subscription_key', 'webhook_secret')
        if field not in secret_fields:
            raise ValueError(f'{field} is not a secret field')
        return decrypt(getattr(self, field))


class PaymentIntent(models.Model):
    """An inbound mobile money payment awaiting provider confirmation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='payment_intents',
    )
    branch = models.ForeignKey(
        'core.Branch', on_delete=models.PROTECT, null=True, blank=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.PROTECT,
        related_name='payment_intents', null=True, blank=True,
    )
    payment = models.OneToOneField(
        'payments.Payment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='momo_intent',
    )

    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    reference = models.CharField(max_length=60, unique=True, db_index=True)
    provider_txn_id = models.CharField(
        max_length=200, blank=True, db_index=True,
        help_text='Provider transaction ID. Unique per provider.',
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    phone = models.CharField(max_length=30, help_text='Payer phone number.')

    status = models.CharField(
        max_length=20, choices=PAYMENT_INTENT_STATUS, default='PENDING',
        db_index=True,
    )
    error = models.TextField(blank=True)

    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'momo_payment_intents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['provider_code', 'provider_txn_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider_code', 'provider_txn_id'],
                condition=models.Q(provider_txn_id__gt=''),
                name='unique_momo_provider_txn_per_provider',
            ),
        ]

    def __str__(self):
        return f'{self.reference} - {self.amount} ({self.status})'

    def save(self, *args, **kwargs):
        if self.client_id and not self.organization_id:
            self.organization_id = self.client.organization_id
        if self.client_id and not self.branch_id:
            self.branch_id = self.client.branch_id
        super().save(*args, **kwargs)


class DisbursementIntent(models.Model):
    """Outbound mobile money payout to a client."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='disbursement_intents',
    )
    branch = models.ForeignKey(
        'core.Branch', on_delete=models.PROTECT, null=True, blank=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT,
        related_name='disbursement_intents',
    )
    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.PROTECT,
        related_name='disbursement_intents', null=True, blank=True,
    )
    journal_entry = models.ForeignKey(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='disbursement_intents',
    )

    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    reference = models.CharField(max_length=60, unique=True, db_index=True)
    provider_txn_id = models.CharField(max_length=200, blank=True, db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    phone = models.CharField(max_length=30, help_text='Recipient phone number.')

    status = models.CharField(
        max_length=20, choices=DISBURSEMENT_INTENT_STATUS, default='PENDING',
        db_index=True,
    )
    error = models.TextField(blank=True)

    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    initiated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'momo_disbursement_intents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['provider_code', 'provider_txn_id']),
        ]

    def __str__(self):
        return f'{self.reference} - {self.amount} ({self.status})'

    def save(self, *args, **kwargs):
        if self.client_id and not self.organization_id:
            self.organization_id = self.client.organization_id
        if self.client_id and not self.branch_id:
            self.branch_id = self.client.branch_id
        super().save(*args, **kwargs)