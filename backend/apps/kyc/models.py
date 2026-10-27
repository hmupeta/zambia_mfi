from django.db import models
from apps.core.models import Organization, Branch
from apps.clients.models import Client
import uuid


# ============================================================
# Choice Constants
# ============================================================
KYC_STATUS_CHOICES = [
    ('NOT_STARTED', 'Not Started'),
    ('IN_PROGRESS', 'In Progress'),
    ('PENDING_REVIEW', 'Pending Review'),
    ('VERIFIED', 'Verified'),
    ('REJECTED', 'Rejected'),
    ('EXPIRED', 'Expired'),
]

KYC_RISK_LEVEL_CHOICES = [
    ('LOW', 'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH', 'High'),
    ('PEP', 'Politically Exposed Person'),
]

KYC_CHECK_TYPE_CHOICES = [
    ('ID_NUMBER', 'ID Number Verification'),
    ('OCR', 'Document OCR Extraction'),
    ('FACE_MATCH', 'Face Match (Selfie vs ID)'),
    ('LIVENESS', 'Liveness Detection'),
    ('ADDRESS', 'Proof of Address'),
    ('PHONE', 'Phone Number Verification'),
    ('EMAIL', 'Email Verification'),
    ('AML', 'AML / Sanctions Screening'),
    ('PEP', 'PEP Screening'),
    ('ADVERSE_MEDIA', 'Adverse Media Check'),
    ('CRB', 'Credit Reference Bureau Check'),
]

KYC_CHECK_RESULT_CHOICES = [
    ('PASS', 'Pass'),
    ('FAIL', 'Fail'),
    ('PENDING', 'Pending'),
    ('MANUAL_REVIEW', 'Manual Review Required'),
    ('SKIPPED', 'Skipped'),
]

ID_DOCUMENT_TYPE_CHOICES = [
    ('NRC', 'National Registration Card'),
    ('PASSPORT', 'Passport'),
    ('DRIVERS_LICENSE', "Driver's Licence"),
    ('VOTER_ID', 'Voter ID'),
]

CLIENT_TYPE_CHOICES = [
    ('INDIVIDUAL', 'Individual'),
    ('BUSINESS', 'Business / SME'),
    ('GROUP', 'Group / Association'),
]


# ============================================================
# Configurable Required Documents
# ============================================================
class KYCDocumentRequirement(models.Model):
    """
    Defines which documents are required for a given client type + risk level.
    Admin-editable so requirements can change without code.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='kyc_document_requirements',
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=30, choices=ID_DOCUMENT_TYPE_CHOICES + [
        ('ADDRESS_PROOF', 'Proof of Address'),
        ('PAYSLIP', 'Payslip'),
        ('BANK_STATEMENT', 'Bank Statement'),
        ('BUSINESS_REG', 'Business Registration'),
        ('PHOTO', 'Passport Photo'),
        ('SELFIE', 'Selfie'),
        ('OTHER', 'Other'),
    ])
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES, default='INDIVIDUAL',
    )
    required_for_risk_levels = models.JSONField(
        default=list, help_text='List of risk levels for which this is required',
    )
    is_mandatory = models.BooleanField(default=True)
    allows_expiry = models.BooleanField(default=False)
    expiry_reminder_days = models.PositiveIntegerField(default=30)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'kyc_document_requirements'
        ordering = ['client_type', 'order']

    def __str__(self):
        return f'{self.code} — {self.name}'


# ============================================================
# KYC Verification (main record per client)
# ============================================================
class KYCVerification(models.Model):
    """
    One verification request per client (may be re-run periodically).
    Tracks the full lifecycle: submit → checks → review → verified/rejected.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='kyc_verifications', editable=False,
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='kyc_verifications',
    )
    verification_number = models.CharField(max_length=40)
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES, default='INDIVIDUAL',
    )

    status = models.CharField(
        max_length=20, choices=KYC_STATUS_CHOICES, default='NOT_STARTED',
    )
    initiated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='initiated_kyc_verifications',
    )
    initiated_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_kyc_verifications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateField(
        null=True, blank=True,
        help_text='When re-verification is required.',
    )
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    # Snapshot of submitted data
    submitted_id_type = models.CharField(
        max_length=20, choices=ID_DOCUMENT_TYPE_CHOICES, blank=True,
    )
    submitted_id_number = models.CharField(max_length=30, blank=True)
    submitted_full_name = models.CharField(max_length=200, blank=True)
    submitted_dob = models.DateField(null=True, blank=True)
    submitted_address = models.TextField(blank=True)

    class Meta:
        db_table = 'kyc_verifications'
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['client', 'status']),
        ]

    def __str__(self):
        return f'{self.verification_number} — {self.client}'


# ============================================================
# KYC Documents
# ============================================================
class KYCDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.ForeignKey(
        KYCVerification, on_delete=models.CASCADE, related_name='documents',
    )
    requirement = models.ForeignKey(
        KYCDocumentRequirement, on_delete=models.PROTECT,
        null=True, blank=True,
    )
    document_type = models.CharField(max_length=30)
    file = models.FileField(upload_to='kyc/documents/')
    file_front = models.FileField(upload_to='kyc/documents/', null=True, blank=True)
    file_back = models.FileField(upload_to='kyc/documents/', null=True, blank=True)

    # Extracted / verified data
    extracted_data = models.JSONField(
        null=True, blank=True,
        help_text='Fields parsed via OCR / manual entry.',
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    expires_on = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_kyc_documents',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kyc_documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.document_type} — {self.verification.verification_number}'


# ============================================================
# KYC Check — individual verification result
# ============================================================
class KYCCheck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.ForeignKey(
        KYCVerification, on_delete=models.CASCADE, related_name='checks',
    )
    check_type = models.CharField(max_length=20, choices=KYC_CHECK_TYPE_CHOICES)
    result = models.CharField(
        max_length=20, choices=KYC_CHECK_RESULT_CHOICES, default='PENDING',
    )
    provider = models.CharField(
        max_length=30, blank=True,
        help_text="e.g. 'smile_id', 'vove_id', 'manual'",
    )
    reference = models.CharField(max_length=100, blank=True)
    raw_response = models.JSONField(null=True, blank=True)
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    error_message = models.TextField(blank=True)
    checked_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kyc_checks'
        ordering = ['-checked_at']

    def __str__(self):
        return f'{self.get_check_type_display()} — {self.result}'


# ============================================================
# Risk Assessment
# ============================================================
class KYCRiskAssessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.OneToOneField(
        KYCVerification, on_delete=models.CASCADE, related_name='risk_assessment',
    )
    risk_level = models.CharField(
        max_length=10, choices=KYC_RISK_LEVEL_CHOICES, default='LOW',
    )
    risk_score = models.IntegerField(default=0)
    is_pep = models.BooleanField(default=False)
    pep_details = models.TextField(blank=True)
    is_sanctioned = models.BooleanField(default=False)
    sanctions_details = models.TextField(blank=True)
    has_adverse_media = models.BooleanField(default=False)
    adverse_media_details = models.TextField(blank=True)
    factors = models.JSONField(
        default=dict, blank=True,
        help_text='Contributing factors and weights.',
    )
    requires_edd = models.BooleanField(
        default=False,
        help_text='Enhanced Due Diligence triggered.',
    )
    edd_notes = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kyc_risk_assessments'

    def __str__(self):
        return f'{self.verification.verification_number} — {self.risk_level}'


# ============================================================
# Review Schedule (periodic re-verification)
# ============================================================
class KYCReviewSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='kyc_review_schedule',
    )
    last_reviewed_at = models.DateField()
    next_review_due = models.DateField()
    risk_level = models.CharField(max_length=10, choices=KYC_RISK_LEVEL_CHOICES)
    review_frequency_months = models.PositiveIntegerField(default=12)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kyc_review_schedules'
        ordering = ['next_review_due']

    def __str__(self):
        return f'{self.client} — next: {self.next_review_due}'


# ============================================================
# Self-Service Token
# ============================================================
class KYCSelfServiceToken(models.Model):
    """
    One-time link sent to clients so they can submit their own KYC
    without logging into the platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='kyc_self_service_tokens',
    )
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kyc_self_service_tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f'Token for {self.client}'