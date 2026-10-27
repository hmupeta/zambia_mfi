from django.db import models
from apps.core.models import Organization, Branch, User
import uuid


class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='clients', editable=False,
    )
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='clients')

    nrc = models.CharField(max_length=20)  # unique per org
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')])
    date_of_birth = models.DateField(null=True, blank=True)
    marital_status = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    employer_name = models.CharField(max_length=100, blank=True)
    employer_address = models.TextField(blank=True)
    home_address = models.TextField(blank=True)
    village_or_area = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=50, blank=True)
    photo = models.ImageField(upload_to='clients/photos/', null=True, blank=True)
    national_id_front = models.ImageField(upload_to='clients/ids/', null=True, blank=True)
    national_id_back = models.ImageField(upload_to='clients/ids/', null=True, blank=True)
    kyc_status = models.CharField(
        max_length=20, default='PENDING',
        choices=[('PENDING', 'Pending'), ('VERIFIED', 'Verified'), ('REJECTED', 'Rejected')],
    )
    credit_score = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'clients'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'nrc'],
                name='unique_client_nrc_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.nrc})"

    def save(self, *args, **kwargs):
        # Derive organization from branch
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)


# ============================================================
# Client Payment Channel (inherits org through client)
# ============================================================
class ClientPaymentChannel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='payment_channels')
    channel_type = models.CharField(max_length=20, choices=[
        ('MTN_MOMO', 'MTN Mobile Money'),
        ('AIRTEL_MONEY', 'Airtel Money'),
        ('BANK', 'Bank'),
        ('CASH', 'Cash'),
    ])
    account_number = models.CharField(max_length=50)
    account_name = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'client_payment_channels'

    def __str__(self):
        return f"{self.client} - {self.channel_type}"


class Guarantor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='guarantors')
    name = models.CharField(max_length=100)
    nrc = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20)
    relationship = models.CharField(max_length=50)
    occupation = models.CharField(max_length=100, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'guarantors'

    def __str__(self):
        return f"{self.name} (guarantor for {self.client})"


class ClientDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=[
        ('NRC', 'National Registration Card'),
        ('PASSPORT', 'Passport'),
        ('COLLATERAL', 'Collateral'),
        ('GUARANTEE_LETTER', 'Guarantee Letter'),
    ])
    file = models.FileField(upload_to='clients/documents/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'client_documents'

    def __str__(self):
        return f"{self.client} - {self.document_type}"