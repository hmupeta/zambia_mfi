from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


# ============================================================
# Organization (Tenant)
# ============================================================
class Organization(models.Model):
    """
    A tenant — one microfinance institution using the platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=50, unique=True, help_text="Short code, e.g., 'acme-mfi'")
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    physical_address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)

    # Subscription / billing
    subscription_tier = models.CharField(
        max_length=20,
        choices=[
            ('TRIAL', 'Trial'),
            ('BASIC', 'Basic'),
            ('PRO', 'Professional'),
            ('ENTERPRISE', 'Enterprise'),
        ],
        default='TRIAL',
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"


# ============================================================
# Branch
# ============================================================
class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='branches',
    )
    code = models.CharField(max_length=20)  # unique per org, not globally
    name = models.CharField(max_length=100)
    parent_branch = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='child_branches',
    )
    physical_address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    is_hq = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'branches'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_branch_code_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# User
# ============================================================
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users',
        null=True, blank=True,
        help_text="Null for platform admins",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name='users',
        null=True, blank=True,
    )
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        max_length=20,
        choices=[
            ('HQ_ADMIN', 'HQ Admin'),
            ('BRANCH_MANAGER', 'Branch Manager'),
            ('LOAN_OFFICER', 'Loan Officer'),
            ('TELLER', 'Teller'),
            ('HR_PAYROLL', 'HR & Payroll Manager'), #
        ],
        default='HQ_ADMIN',
    )
    is_platform_admin = models.BooleanField(
        default=False,
        help_text="Platform-level superuser with cross-tenant access.",
    )

    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'users'

    def __str__(self):
        org = self.organization.code if self.organization else 'PLATFORM'
        return f"{self.username} ({self.role} @ {org})"

    @property
    def is_tenant_user(self):
        return self.organization_id is not None

# ============================================================
# SITE SETTINGS (Singleton)
# ============================================================
class SiteSettings(models.Model):
    """Global platform branding + contact info. Only one row."""
    id = models.PositiveIntegerField(primary_key=True, default=1, editable=False)

    # Identity
    site_name = models.CharField(max_length=100, default='Nimbus Investment Ltd')
    site_short_name = models.CharField(max_length=50, default='NIMBUS')
    site_tagline = models.CharField(
        max_length=200,
        default='Modern lending infrastructure for Zambian MFIs',
    )
    logo = models.ImageField(upload_to='site/', null=True, blank=True)
    favicon = models.ImageField(upload_to='site/', null=True, blank=True)

    # Branding (hex colors)
    primary_color = models.CharField(max_length=20, default='#0f172a')
    accent_color = models.CharField(max_length=20, default='#2563eb')
    background_color = models.CharField(max_length=20, default='#ffffff')

    # Meta
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    # Contact
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_address = models.CharField(max_length=200, blank=True)

    # Social
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)

    # Footer
    footer_copyright = models.CharField(max_length=200, blank=True)
    footer_note = models.CharField(max_length=200, blank=True)

    # Nav links (URL paths)
    login_url = models.CharField(max_length=200, default='/admin/')
    api_docs_url = models.CharField(max_length=200, default='/api/docs/')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'site_settings'
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ============================================================
# LANDING SECTIONS
# ============================================================
class LandingSection(models.Model):
    """A top-level section on the landing page. Order + visibility controlled here."""
    TYPE_CHOICES = [
        ('hero', 'Hero'),
        ('trust', 'Trust Bar'),
        ('problem', 'Problem / Solution'),
        ('features', 'Features'),
        ('how', 'How It Works'),
        ('stats', 'Stats'),
        ('pricing', 'Pricing'),
        ('faq', 'FAQ'),
        ('cta', 'Final CTA'),
    ]
    BACKGROUND_CHOICES = [
        ('white', 'White'),
        ('cream', 'Cream'),
        ('dark', 'Dark (brand color)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(
        max_length=50, unique=True,
        help_text="Identifier used in template (e.g. 'hero', 'features')",
    )
    section_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    eyebrow = models.CharField(max_length=100, blank=True, help_text="Small label above the title")
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.TextField(blank=True)
    background = models.CharField(max_length=10, choices=BACKGROUND_CHOICES, default='white')
    anchor = models.SlugField(max_length=50, blank=True, help_text="Optional #anchor for nav links")
    is_visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Section-specific extras (e.g. hero CTA, stats number)",
    )

    class Meta:
        db_table = 'landing_sections'
        ordering = ['order', 'key']
        verbose_name = 'Landing Section'
        verbose_name_plural = 'Landing Sections'

    def __str__(self):
        return f"{self.order:02d} · {self.get_section_type_display()} ({self.key})"


class SectionItem(models.Model):
    """A repeatable item within a section (feature card, pricing plan, FAQ entry, etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        LandingSection, on_delete=models.CASCADE, related_name='items',
    )
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50, blank=True,
        help_text="Icon name (see apps/core/templatetags/nimbus_icons.py)",
    )
    badge = models.CharField(max_length=50, blank=True, help_text="e.g. 'MOST POPULAR'")
    image = models.ImageField(upload_to='landing/items/', null=True, blank=True)
    cta_text = models.CharField(max_length=50, blank=True)
    cta_url = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'landing_section_items'
        ordering = ['order', 'title']
        verbose_name = 'Section Item'
        verbose_name_plural = 'Section Items'

    def __str__(self):
        return f"{self.section.key} · {self.title}"

# ============================================================
# CMS — Pages
# ============================================================
class Page(models.Model):
    TEMPLATE_CHOICES = [
        ('default', 'Default'),
        ('about', 'About Us'),
        ('contact', 'Contact Us'),
        ('legal', 'Legal / Terms'),
        ('blank', 'Blank (no hero)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=200)
    subtitle = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to='pages/heroes/', null=True, blank=True)
    template = models.CharField(max_length=20, choices=TEMPLATE_CHOICES, default='default')

    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    is_published = models.BooleanField(default=True)
    show_in_header = models.BooleanField(default=False)
    show_in_footer = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pages'
        ordering = ['order', 'title']

    def __str__(self):
        return self.title


class ContentBlock(models.Model):
    """A flexible, typed content block for pages."""
    BLOCK_TYPE_CHOICES = [
        ('heading', 'Heading'),
        ('paragraph', 'Paragraph'),
        ('image_text', 'Image + Text (2-col)'),
        ('grid', 'Grid of Cards'),
        ('faq', 'FAQ / Accordion'),
        ('stats', 'Stats Row'),
        ('cta', 'Call to Action'),
        ('quote', 'Pull Quote'),
        ('markdown', 'Rich Text (Markdown)'),
        ('html', 'Custom HTML'),
        ('divider', 'Divider'),
    ]
    ALIGNMENT_CHOICES = [('left', 'Left'), ('center', 'Center'), ('right', 'Right')]
    BACKGROUND_CHOICES = [('white', 'White'), ('cream', 'Cream'), ('dark', 'Dark')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='blocks')
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES)
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True, help_text='Main text. Markdown supported in markdown blocks.')
    image = models.ImageField(upload_to='pages/blocks/', null=True, blank=True)
    cta_text = models.CharField(max_length=50, blank=True)
    cta_url = models.CharField(max_length=200, blank=True)
    alignment = models.CharField(max_length=10, choices=ALIGNMENT_CHOICES, default='left')
    background = models.CharField(max_length=10, choices=BACKGROUND_CHOICES, default='white')
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text='Block-specific extras (e.g. grid items, stats, faq pairs)',
    )
    is_visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'content_blocks'
        ordering = ['order']

    def __str__(self):
        return f'{self.page.slug} · {self.get_block_type_display()}'


# ============================================================
# CMS — Blog
# ============================================================
class BlogPost(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('published', 'Published')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    excerpt = models.TextField(blank=True, max_length=400)
    body = models.TextField(help_text='Markdown supported.')
    cover_image = models.ImageField(upload_to='blog/covers/', null=True, blank=True)
    category = models.CharField(max_length=50, blank=True)
    tags = models.CharField(max_length=200, blank=True, help_text='Comma-separated')
    author = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    published_at = models.DateTimeField(null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)

    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blog_posts'
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]


# ============================================================
# CMS — Navigation
# ============================================================
class NavItem(models.Model):
    MENU_CHOICES = [('header', 'Header'), ('footer', 'Footer')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu = models.CharField(max_length=10, choices=MENU_CHOICES)
    label = models.CharField(max_length=50)
    url = models.CharField(max_length=200, blank=True, help_text='Leave blank to auto-use the linked page')
    page = models.ForeignKey(Page, on_delete=models.SET_NULL, null=True, blank=True)
    open_in_new_tab = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'nav_items'
        ordering = ['menu', 'order']

    def __str__(self):
        return f'[{self.menu}] {self.label}'

    def get_href(self):
        if self.url:
            return self.url
        if self.page:
            return f'/pages/{self.page.slug}/'
        return '#'


# ============================================================
# CMS — Contact Submissions
# ============================================================
class ContactSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contact_submissions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} <{self.email}>'


# ============================================================
# Audit Log
# ============================================================
class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs',
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField(null=True, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.action} on {self.entity_type}"

 #  — additions - to facilitate Settings and User Management

class OrganizationSettings(models.Model):
    """
    Singleton per organization — global site configuration.
    One row per organization. Enforced by OneToOneField.
    """
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE,
        related_name='settings',
    )

    # ── Organisation ──────────────────────────────────────
    legal_name = models.CharField(max_length=200, blank=True)
    trading_name = models.CharField(max_length=200, blank=True)
    tin = models.CharField(
        max_length=20, blank=True,
        help_text='Zambia Revenue Authority Taxpayer Identification Number',
    )
    pacra_number = models.CharField(max_length=30, blank=True)
    boz_license_number = models.CharField(max_length=30, blank=True)
    physical_address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='branding/', null=True, blank=True)
    favicon = models.ImageField(upload_to='branding/', null=True, blank=True)

    # ── Branding ──────────────────────────────────────────
    accent_color = models.CharField(max_length=7, default='#B45309')
    primary_color = models.CharField(max_length=7, default='#0A0A0A')

    # ── Financial ─────────────────────────────────────────
    default_currency = models.CharField(max_length=3, default='ZMW')
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    default_interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Annual percentage (e.g., 24.00 for 24%)',
    )
    default_penalty_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
    )
    default_grace_period_days = models.PositiveSmallIntegerField(default=30)

    # ── Operations ────────────────────────────────────────
    loan_approval_threshold = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Amount above which HQ approval is required.',
    )
    expense_approval_threshold = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
    )
    password_min_length = models.PositiveSmallIntegerField(default=8)
    session_timeout_minutes = models.PositiveSmallIntegerField(default=60)
    enable_2fa = models.BooleanField(default=False)

    # ── Notifications ─────────────────────────────────────
    sms_sender_id = models.CharField(
        max_length=11, blank=True,
        help_text='GSM 11-character sender ID (e.g., NIMBUS)',
    )
    sms_gateway_url = models.URLField(blank=True)
    # NOTE: store encrypted in production (use cryptography.Fernet).
    sms_gateway_api_key = models.CharField(max_length=200, blank=True)
    email_from_address = models.EmailField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organization_settings'
        verbose_name_plural = 'Organization settings'

    def __str__(self):
        return f"Settings for {self.organization.name}"

    @classmethod
    def for_org(cls, org):
        """Get-or-create the settings singleton for an organization."""
        obj, _ = cls.objects.get_or_create(organization=org)
        return obj


class FeatureFlag(models.Model):
    """
    Toggle features on/off per organization, optionally scoped to branches.
    Leave `enabled_for_branches` empty to apply to all branches.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='feature_flags',
    )
    key = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    enabled_for_branches = models.ManyToManyField(
        'Branch', blank=True,
        related_name='feature_flags',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feature_flags'
        ordering = ['key']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'key'],
                name='unique_feature_flag_key_per_org',
            ),
        ]

    def __str__(self):
        return f"{self.key} ({'on' if self.enabled else 'off'})"


# ============================================================
# LEGAL & COMPLIANCE — Agreements and Acceptance
# ============================================================

class LegalDocument(models.Model):
    """
    Versioned legal documents (T&C, DPA, SLA) provided by Nimbus Solutions.
    """
    DOC_TYPE_CHOICES = [
        ('TERMS', 'Master SaaS Agreement & Terms of Service'),
        ('DPA', 'Data Processing Agreement (Zambia DPA 2021)'),
        ('SLA', 'Service Level Agreement'),
        ('PRIVACY', 'Privacy Policy'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    version = models.CharField(max_length=20, help_text="e.g., '1.0', '2.1'")
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="The full legal text (Markdown supported).")
    
    effective_date = models.DateField(help_text="Date from which this version is legally binding.")
    is_active = models.BooleanField(
        default=True, 
        help_text="Set to True if this is the current version MFIs must sign."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'legal_documents'
        ordering = ['-effective_date', 'doc_type']
        constraints = [
            models.UniqueConstraint(
                fields=['doc_type', 'version'],
                name='unique_legal_doc_version',
            ),
        ]

    def __str__(self):
        return f"{self.get_doc_type_display()} (v{self.version}) - {'Active' if self.is_active else 'Archived'}"


class OrganizationAgreement(models.Model):
    """
    Tracks the digital acceptance of legal documents by an Organization (MFI).
    This serves as the binding electronic signature under the ECT Act.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending Signature'),
        ('SIGNED', 'Signed & Active'),
        ('EXPIRED', 'Expired / Superseded'),
        ('TERMINATED', 'Terminated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='agreements'
    )
    document = models.ForeignKey(
        LegalDocument, 
        on_delete=models.PROTECT, 
        related_name='organization_acceptances'
    )
    
    # E-Signature Data (ECT Act Compliance)
    signed_by = models.ForeignKey(
        'core.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='signed_agreements'
    )
    signed_by_name = models.CharField(max_length=200, help_text="Full legal name of signatory")
    signed_by_title = models.CharField(max_length=100, help_text="e.g., Managing Director, CEO")
    
    signature_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, help_text="Browser/Device info at time of signing")
    
    signed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organization_agreements'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'document'],
                name='unique_org_document_acceptance',
            ),
        ]

    def __str__(self):
        return f"{self.organization.code} - {self.document.doc_type} v{self.document.version} ({self.status})"