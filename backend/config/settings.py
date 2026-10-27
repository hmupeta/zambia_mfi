"""
Django settings for Zambia MFI Platform.
"""

from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# Authentication
# ============================================================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/app/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# ============================================================
# Security
# ============================================================
SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'django-insecure-s$0y322s8&3chrznfk^l+m^wt7$yb+dzvdek6so3cgi!riwqfz',
)
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# ============================================================
# Applications
# ============================================================
INSTALLED_APPS = [
    # Django built-ins
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',

    # Local apps
    'apps.core.apps.CoreConfig',
    'apps.clients.apps.ClientsConfig',
    'apps.loans.apps.LoansConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.momo',
    # Provider adapters
    'apps.aggregators.apps.AggregatorsConfig',
    'apps.airtel.apps.AirtelConfig',
    'apps.zamtel.apps.ZamtelConfig',

    'apps.reports.apps.ReportsConfig',
    'apps.accounting.apps.AccountingConfig',
    'apps.expenses.apps.ExpensesConfig',
    'apps.restructures.apps.RestructuresConfig',
    'apps.origination.apps.OriginationConfig',
    'apps.kyc.apps.KycConfig',
    'apps.notifications', 
    'apps.portal', 
    'apps.payroll',
]


# ============================================================
# Middleware
# ============================================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # <-- required for CORS
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'apps.portal.middleware.PortalClientMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.OrgStatusMiddleware',
]

ROOT_URLCONF = 'config.urls'


# ============================================================
# Templates
# ============================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR.parent / 'frontend' / 'templates'],   # <-- points to ../../frontend/templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ============================================================
# Database (PostgreSQL)
# ============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'zambia_mfi'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'admin'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}


# ============================================================
# Password validation
# ============================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ============================================================
# Internationalization
# ============================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lusaka'
USE_I18N = True
USE_TZ = True


# ============================================================
# Static & media
# ============================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR.parent / 'frontend' / 'static']     # <-- points to ../../frontend/static

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================
# Custom user model
# ============================================================
AUTH_USER_MODEL = 'core.User'


# ============================================================
# CORS - allow the React frontend during development
# ============================================================
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8081',     
    'http://127.0.0.1:8081',      
]

CORS_ALLOW_CREDENTIALS = True


# ============================================================
# Django REST Framework
# ============================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'login': '10/min',
    },
    'URL_FORMAT_OVERRIDE': None,
}


# ============================================================
# JWT
# ============================================================

# config/settings.py

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'TOKEN_OBTAIN_SERIALIZER': 'apps.core.serializers_auth.NimbusTokenObtainPairSerializer',
    }


# ============================================================
# drf-spectacular (Swagger UI)
# ============================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'Zambia MFI Platform API',
    'DESCRIPTION': (
        'Multi-tenant, multi-branch loan management platform for Zambian '
        'microfinance institutions.\n\n'
        '**Tenancy model:** Every request is scoped to the caller\'s '
        'organization (tenant), derived from the JWT. Platform admins '
        'can see all tenants; tenant users see only their own.\n\n'
        '**Roles:** `HQ_ADMIN`, `BRANCH_MANAGER`, `LOAN_OFFICER`, `TELLER`.\n\n'
        '**How to authenticate:**\n'
        '1. `POST /api/auth/token/` with `{"username","password"}`\n'
        '2. Copy the `access` token\n'
        '3. Click **Authorize** above and paste it (Swagger auto-prefixes "Bearer ")\n'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,

    # UI bundling
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',

    # Contact / license
    'CONTACT': {
        'name': 'Zambia MFI Platform',
        'email': 'platform@zambiamfi.local',
    },
    'LICENSE': {
        'name': 'Proprietary',
    },

    # Collapse examples
    'COMPONENT_SPLIT_REQUEST': True,

    # Tag grouping
    'TAGS_SORTING': 'defined',

    # ============================================================
    # Enum name overrides (avoid drf-spectacular naming collisions)
    # ============================================================
    'ENUM_NAME_OVERRIDES': {
        # Single shared payment-method enum used by:
        #   Loan.disbursement_channel, Payment.payment_method,
        #   Expense.payment_method, WalletTransaction.source_wallet/dest_wallet
        'PaymentMethodEnum': 'apps.core.constants.PAYMENT_METHOD_CHOICES',

        # Restructure enums (avoid collisions with other `status` / `action` fields)
        'RestructureStatusEnum': 'apps.restructures.models.RESTRUCTURE_STATUS_CHOICES',
        'RestructureTypeEnum': 'apps.restructures.models.RESTRUCTURE_TYPE_CHOICES',
        'RestructureReasonEnum': 'apps.restructures.models.RESTRUCTURE_REASON_CHOICES',
        'LoanStatusEnum': 'apps.loans.models.LOAN_STATUS_CHOICES',
        'PaymentStatusEnum': 'apps.payments.models.PAYMENT_STATUS_CHOICES',
        'IntentStatusEnum': 'apps.momo.models.PAYMENT_INTENT_STATUS',
        'MeetingFrequencyEnum': 'apps.loans.models.MEETING_FREQUENCY_CHOICES'
    },

    'TAGS': [
        {
            'name': 'Auth',
            'description': (
                '## Authentication\n\n'
                'Issues and refreshes JSON Web Tokens (JWT). Every other endpoint '
                'requires a valid access token passed as `Authorization: Bearer <token>`.\n\n'
                '**Flow:**\n'
                '1. `POST /api/auth/token/` with `{username, password}`\n'
                '2. Receive `{access, refresh}`\n'
                '3. Send `access` on subsequent requests\n'
                '4. When `access` expires (12h), use `refresh` on `/api/auth/token/refresh/`\n\n'
                '**JWT claims:** `user_id`, `username`, `role`, `organization_id`, '
                '`organization_code`, `branch_id`, `branch_code`, `is_platform_admin`.'
            ),
        },
        {
            'name': 'Organizations',
            'description': (
                '## Tenant Management (Platform Admin Only)\n\n'
                'A **tenant** is one microfinance institution. Root of the multi-tenant '
                'hierarchy - all branches, users, clients, loans, payments, and journals '
                'are scoped to exactly one organization.\n\n'
                '**Only users with `is_platform_admin = true` can call these endpoints.**\n\n'
                '**Onboarding flow:**\n'
                '1. `POST /api/auth/organizations/` - create the tenant\n'
                '2. (System) auto-creates an HQ branch\n'
                '3. Create the tenant\'s first HQ admin user\n'
                '4. Seed the Chart of Accounts via management command\n\n'
                '**Subscription tiers:** `TRIAL`, `BASIC`, `PRO`, `ENTERPRISE`.'
            ),
        },
        {
            'name': 'Branches',
            'description': (
                '## Branch Management\n\n'
                'Operating units within a tenant. Each branch has its own wallet, client '
                'portfolio, loan book, and payment stream.\n\n'
                '**Hierarchy:** Model HQ -> Regional -> Branch via `parent_branch`. '
                'Every tenant must have exactly one `is_hq = true` branch.\n\n'
                '**Visibility:** `HQ_ADMIN` sees all branches; other roles see only their own.'
            ),
        },
        {
            'name': 'Users',
            'description': (
                '## Staff Management\n\n'
                '### Roles\n'
                '| Role | Scope | Duties |\n'
                '|------|-------|--------|\n'
                '| `HQ_ADMIN` | Whole tenant | Branches, users, products, reports |\n'
                '| `BRANCH_MANAGER` | Own branch | Approve/disburse loans |\n'
                '| `LOAN_OFFICER` | Own branch | Create clients, originate loans |\n'
                '| `TELLER` | Own branch | Record payments, manage cash |\n\n'
                'Every user must belong to an `organization` (except platform admins). '
                'Regular staff must also have a `branch`.\n\n'
                '**Password policy:** Minimum 10 characters.'
            ),
        },
        {
            'name': 'Clients',
            'description': (
                '## Borrower Records\n\n'
                'Full KYC profile per borrower, scoped to one organization and one branch.\n\n'
                '**KYC status:** `PENDING` -> `VERIFIED` (or `REJECTED`). '
                'Only `VERIFIED` clients should receive loans.\n\n'
                '**NRC is unique per organization** - the same person can be a client '
                'of two different MFIs on the platform.'
            ),
        },
        {
            'name': 'Client Payment Channels',
            'description': (
                '## Client Payment Channels\n\n'
                'Mobile money accounts, bank accounts, or cash-designated channels for '
                'each client. Used to route disbursements and recognize inbound repayments.\n\n'
                '**Channel types:** `MTN_MOMO`, `AIRTEL_MONEY`, `BANK`, `CASH`.\n\n'
                'A client can have multiple channels; mark one as `is_default = true` to '
                'auto-select it during disbursement.'
            ),
        },
        {
            'name': 'Guarantors',
            'description': (
                '## Guarantors\n\n'
                'Co-signers who back a client\'s loan. Common for individual loans and '
                'group lending where the group collectively guarantees each member.\n\n'
                'Stores: name, NRC, phone, relationship to the client, occupation, and '
                'monthly income - used during loan appraisal to assess the strength of '
                'the guarantee.'
            ),
        },
        {
            'name': 'Client Documents',
            'description': (
                '## Client Documents\n\n'
                'Scanned and uploaded documents attached to a client profile.\n\n'
                '**Document types:** `NRC`, `PASSPORT`, `COLLATERAL`, `GUARANTEE_LETTER`.\n\n'
                'Every upload records who uploaded it and when - for KYC audit trails.\n\n'
                '**Storage:** Files are stored under `media/clients/documents/` and '
                'referenced by URL. In production, swap to S3 or equivalent.'
            ),
        },
        {
            'name': 'Loan Products',
            'description': (
                '## Loan Products\n\n'
                'Templates that define the parameters for a class of loans.\n\n'
                '**Key parameters:**\n'
                '- Amount range (min/max)\n'
                '- Tenure (months)\n'
                '- Interest method: `FLAT`, `REDUCING_BALANCE`, `DAILY`\n'
                '- Interest rate and penalty rate\n'
                '- Repayment frequency: `DAILY`, `WEEKLY`, `BIWEEKLY`, `MONTHLY`\n'
                '- Grace period (days)\n'
                '- Whether guarantor or collateral is required\n\n'
                '**Only `HQ_ADMIN` can create or edit products.** '
                'Each product can be scoped to specific branches via Branch Loan Products.'
            ),
        },
        {
            'name': 'Branch Loan Products',
            'description': (
                '## Branch Loan Products\n\n'
                'Maps a loan product to specific branches. Use this when a product '
                'should only be offered at certain locations (e.g. an agricultural loan '
                'only at rural branches).\n\n'
                '**Creating a mapping means the product is available at that branch.** '
                'Removing it disables the product for new loans at that branch, but '
                'existing loans remain unaffected.\n\n'
                '**Only `HQ_ADMIN` can manage mappings.**'
            ),
        },
        {
            'name': 'Loan Groups',
            'description': (
                '## Loan Groups (Solidarity Lending)\n\n'
                'Groups of clients who collectively guarantee each other\'s loans - a '
                'classic microfinance model.\n\n'
                'Each group has:\n'
                '- A **leader** (usually the longest-standing member)\n'
                '- A **branch** of operation\n'
                '- A set of **members** managed via the Loan Group Members endpoint\n\n'
                'Group loans use these entities to establish joint liability: if one '
                'member defaults, the group is collectively responsible.'
            ),
        },
        {
            'name': 'Loan Group Members',
            'description': (
                '## Loan Group Members\n\n'
                'Links clients into loan groups and designates the group leader.\n\n'
                '**Rules:**\n'
                '- A client can belong to only one group at a time\n'
                '- Exactly one member should be marked `is_leader = true`\n'
                '- A member cannot be added to a group in a different organization\n\n'
                'When a group loan is disbursed, all members become jointly liable for '
                'repayment.'
            ),
        },
        {
            'name': 'Loans',
            'description': (
                '## Loan Lifecycle\n\n'
                '### Status flow\n'
                '`PENDING` -> `APPROVED` -> `ACTIVE` (after disburse) -> `CLOSED`\n'
                'Or `DEFAULTED` if written off.\n\n'
                '### Actions\n'
                '- `POST /loans/{id}/approve/` - Branch Manager or HQ\n'
                '- `POST /loans/{id}/disburse/` - auto-posts GL entry\n'
                '- `GET  /loans/{id}/schedule/` - full installment plan\n\n'
                '### Interest methods\n'
                '- **FLAT** - simple interest on original principal\n'
                '- **REDUCING_BALANCE** - interest on outstanding principal (annuity)\n'
                '- **DAILY** - daily accrual, common in payday-style products'
            ),
        },
                {
            'name': 'Workflow Templates',
            'description': (
                '## Loan Workflow Templates\n\n'
                'Configurable approval pipelines. Each template has ordered stages '
                'with role requirements and SLAs.\n\n'
                '### Example\n'
                '1. Loan Officer Review (LOAN_OFFICER, 24h SLA)\n'
                '2. Branch Manager Approval (BRANCH_MANAGER, 48h SLA, **final**)\n\n'
                '**Only `HQ_ADMIN`** can manage templates.'
            ),
        },
        {
            'name': 'Loan Applications',
            'description': (
                '## Loan Origination\n\n'
                'A client\'s request for credit before it becomes a Loan.\n\n'
                '### Status flow\n'
                '`DRAFT` → `SUBMITTED` → `UNDER_REVIEW` → `APPROVED` / `REJECTED`\n'
                '(or `RETURNED`, `WITHDRAWN`)\n\n'
                '### Workflow actions\n'
                '- `POST .../submit/` — submit for review\n'
                '- `POST .../advance/` — move to next stage (approves if final stage)\n'
                '- `POST .../reject/` — reject the application\n'
                '- `POST .../return_to_applicant/` — send back to first stage\n'
                '- `POST .../withdraw/` — withdraw\n\n'
                '### On approval\n'
                'A `Loan` record is created automatically in `APPROVED` status, ready to disburse.'
            ),
        },
        {
            'name': 'Origination - Documents',
            'description': 'Supporting documents attached to applications (NRC, payslips, bank statements, collateral photos).',
        },
        {
            'name': 'Origination - Transitions',
            'description': 'Immutable log of every stage change. Read-only.',
        },
        {
            'name': 'Origination - Reviews',
            'description': 'Reviewer notes with recommendations: approve / reject / return / flag.',
        },
        {
            'name': 'Tasks',
            'description': (
                '## Task Management\n\n'
                'Follow-up tasks assigned to users. Polymorphic — links to loan applications, '
                'loans, clients, or general.\n\n'
                '### Use cases\n'
                '- Approval queue items (auto-created on stage transitions)\n'
                '- Client visit follow-ups\n'
                '- Payment reminders\n'
                '- Disbursement queue\n\n'
                '### Filtering\n'
                'Use `?assigned_to=<user-id>` to see a specific user\'s tasks, '
                'or `GET /api/origination/tasks/mine/` for the caller\'s own.'
            ),
        },
        {
            'name': 'Installments',
            'description': (
                '## Loan Installments\n\n'
                'The repayment schedule of a loan - one row per installment. Generated '
                'when the loan is created, based on the product\'s repayment frequency.\n\n'
                '**Each installment tracks:**\n'
                '- Due date and installment number\n'
                '- Principal, interest, penalty (expected)\n'
                '- Amount paid so far\n'
                '- Status: `PENDING`, `PARTIAL`, `PAID`, `OVERDUE`\n\n'
                '**Read-only endpoint** - installments are updated automatically by the '
                'payment allocation engine. Manual edits are not permitted.'
            ),
        },
        {
            'name': 'Payments',
            'description': (
                '## Payment Recording\n\n'
                'Captures every repayment against a loan.\n\n'
                '### What happens when you POST a payment\n'
                '1. Find the oldest unpaid installments\n'
                '2. Allocate across **principal -> interest -> penalty**\n'
                '3. Update installment balances and statuses\n'
                '4. Update the loan `balance_due` (close loan if fully paid)\n'
                '5. **Post a balanced journal entry** - '
                '`DR Cash/Bank/MoMo` / `CR Loans Receivable + Interest Income + Penalty Income`\n'
                '6. Update the branch wallet\n\n'
                '### Payment methods\n'
                '`CASH`, `MTN_MOMO`, `AIRTEL_MONEY`, `BANK`\n\n'
                '**Atomicity:** If the journal entry fails, the entire payment rolls back. '
                'The books never go out of balance.'
            ),
        },
        {
            'name': 'Payment Allocations',
            'description': (
                '## Payment Allocations\n\n'
                'Shows exactly how a single payment was split across installments and '
                'across principal / interest / penalty components.\n\n'
                'Every payment produces one or more allocation records - one per '
                'installment it touched.\n\n'
                '**Read-only** - allocations are created by the payment engine and are '
                'the audit trail behind GL entries.'
            ),
        },
        {
            'name': 'Wallets',
            'description': (
                '## Branch Wallets\n\n'
                'Each branch maintains three running balances:\n'
                '- **Cash on hand** - physical cash in the branch vault\n'
                '- **Mobile money** - combined MTN MoMo + Airtel Money balance\n'
                '- **Bank** - funds in the branch operating account\n\n'
                'Use `GET /payments/wallets/my_wallet/` to fetch the caller\'s branch wallet '
                'without needing its UUID.\n\n'
                'Wallets are updated automatically by payments and disbursements. '
                'Manual reconciliation via `last_reconciled_at`.'
            ),
        },
        {
            'name': 'Wallet Transactions',
            'description': (
                '## Wallet Transactions\n\n'
                'Every movement in or out of a branch wallet: disbursements, loan '
                'collections, transfers between branches, and expenses.\n\n'
                '**Transaction types:** `DISBURSEMENT`, `LOAN_COLLECTION`, '
                '`TRANSFER_IN`, `TRANSFER_OUT`, `EXPENSE`.\n\n'
                '**Read-only** - each record carries a reference to the source document '
                '(payment number, loan number, or transfer ref) for reconciliation.'
            ),
        },
        {
            'name': 'Accounting - Chart of Accounts',
            'description': (
                '## Chart of Accounts (General Ledger)\n\n'
                'Each tenant has its own Chart of Accounts, seeded via '
                '`python manage.py seed_chart_of_accounts`.\n\n'
                '### Account types\n'
                '| Type | Prefix | Normal balance |\n'
                '|------|--------|----------------|\n'
                '| Asset | 1xxx | Debit |\n'
                '| Liability | 2xxx | Credit |\n'
                '| Equity | 3xxx | Credit |\n'
                '| Income | 4xxx | Credit |\n'
                '| Expense | 5xxx | Debit |\n\n'
                '**Key accounts:** `1010` Cash, `1020` Bank, `1030` MoMo, '
                '`1100` Loans Receivable, `1130` Interest Receivable, '
                '`1200` Allowance for Loan Losses, `2300` Loan Loss Provision, '
                '`4000` Interest Income, `5000` Loan Loss Expense.\n\n'
                '**Only `HQ_ADMIN` can create, edit, or deactivate accounts.** '
                'Once used in a posted entry, an account cannot be deleted.'
            ),
        },
        {
            'name': 'Accounting - Journal Entries',
            'description': (
                '## Double-Entry Journal Entries\n\n'
                'Every financial event produces one balanced `JournalEntry` with two or '
                'more `JournalLine` legs. Debits must equal credits.\n\n'
                '### Automatically generated by\n'
                '- **Loan Disbursement** - `DR Loans Receivable` / `CR Cash or MoMo`\n'
                '- **Loan Repayment** - `DR Cash or MoMo` / `CR Loans Receivable + Interest + Penalty`\n'
                '- **Interest Accrual** (daily job) - `DR Interest Receivable` / `CR Interest Income`\n'
                '- **Penalty Accrual** - `DR Penalties Receivable` / `CR Penalty Income`\n'
                '- **Loan Loss Provision** - `DR Loan Loss Expense` / `CR Loan Loss Provision`\n'
                '- **Write-Off** - `DR Loan Loss Provision` / `CR Loans Receivable`\n\n'
                '### Source tracking\n'
                'Each entry stores `source_type` and `source_id` for full drill-through.\n\n'
                '### Manual entries\n'
                'Use `POST /accounting/journal-entries/manual/` for adjustments.\n\n'
                '### Reversal\n'
                'Entries are **never deleted** - reverse via the reversal mechanism.'
            ),
        },
        {
            'name': 'Accounting - Provisions',
            'description': (
                '## Loan Loss Provisioning\n\n'
                'Implements the **Bank of Zambia Microfinance Classification & '
                'Provisioning Directives, 2018**.\n\n'
                '| Days Past Due | Classification | Provision |\n'
                '|---------------|----------------|-----------|\n'
                '| 0 | Performing | 1% |\n'
                '| 1-30 | Watch | 5% |\n'
                '| 31-90 | Substandard | 25% |\n'
                '| 91-180 | Doubtful | 75% |\n'
                '| 181+ | Loss | 100% |\n\n'
                'POST `/accounting/provisions/run/` triggers provisioning for the tenant: '
                'computes DPD, classifies, and posts the **movement** to the GL.\n\n'
                '**Should run daily** via scheduler. Idempotent per date.'
            ),
        },
        {
            'name': 'Accounting - Financial Statements',
            'description': (
                '## Financial Statements\n\n'
                'Real-time reports derived directly from the General Ledger - no batch '
                'jobs, no manual aggregation.\n\n'
                '### Trial Balance\n'
                '`GET /accounting/reports/trial-balance/?as_of=YYYY-MM-DD`\n\n'
                '### Income Statement (P&L)\n'
                '`GET /accounting/reports/income-statement/?from=YYYY-MM-DD&to=YYYY-MM-DD`\n\n'
                '### Balance Sheet\n'
                '`GET /accounting/reports/balance-sheet/?as_of=YYYY-MM-DD` - includes a '
                '`balanced` boolean verifying the accounting equation.\n\n'
                '**All statements are tenant-scoped.**'
            ),
        },
        {
            'name': 'Accounting - BoZ Reports',
            'description': (
                '## Bank of Zambia Prudential Returns\n\n'
                'Regulatory reports required under the '
                '**Banking and Financial Services Act, 2026**.\n\n'
                '### NPL Return\n'
                '`GET /accounting/reports/npl-return/?as_of=YYYY-MM-DD`\n\n'
                '### Portfolio at Risk\n'
                '`GET /accounting/reports/portfolio-at-risk/?as_of=YYYY-MM-DD` - '
                'returns PAR 1, PAR 7, PAR 30, PAR 60, PAR 90 as percentages.\n\n'
                '**BoZ benchmarks:** PAR 30 under 5% and PAR 90 under 3% for a healthy book.\n\n'
                '**Only `HQ_ADMIN`** can access the full NPL return. PAR is available to '
                'HQ and Branch Managers.'
            ),
        },
                {
            'name': 'Notifications - Templates',
            'description': (
                '## Notification Templates\n\n'
                'Reusable message templates for SMS and WhatsApp.\n\n'
                '### Placeholder syntax\n'
                'Use `{{variable}}` in the template body:\n'
                '- `LOAN_DISBURSED`: `{{first_name}}`, `{{loan_number}}`, '
                '`{{amount}}`, `{{maturity_date}}`\n'
                '- `PAYMENT_RECEIVED`: `{{first_name}}`, `{{amount}}`, '
                '`{{loan_number}}`, `{{payment_number}}`, `{{balance}}`\n'
                '- `PAYMENT_DUE`: `{{first_name}}`, `{{amount}}`, '
                '`{{due_date}}`, `{{loan_number}}`\n'
                '- `OVERDUE_NOTICE`: `{{first_name}}`, `{{loan_number}}`, '
                '`{{days_overdue}}`, `{{amount}}`\n\n'
                '**Only `HQ_ADMIN`** can create or edit templates.'
            ),
        },
        {
            'name': 'Notifications - Logs',
            'description': (
                '## Notification Logs\n\n'
                'Immutable log of every SMS/WhatsApp message sent.\n\n'
                '### What\'s captured\n'
                '- Recipient phone + name\n'
                '- Channel, template code, rendered body\n'
                '- Provider response (Africa\'s Talking / WhatsApp Cloud)\n'
                '- Status: `QUEUED`, `SENT`, `DELIVERED`, `FAILED`\n'
                '- Timestamps, error messages, retry count\n\n'
                '### Automatic sends\n'
                'Messages are triggered automatically by:\n'
                '- **Loan disbursement** — via signal on `Loan.status`\n'
                '- **Payment received** — via signal on `Payment` creation\n'
                '- **Due-date reminders** — via scheduled management command\n'
                '- **Overdue notices** — via scheduled management command\n\n'
                '### Ad-hoc test\n'
                'HQ admins can use `POST /api/notifications/logs/send_test/` '
                'to send a one-off message for testing.'
            ),
        },
                {
            'name': 'Loan Restructures',
            'description': (
                '## Loan Restructuring & Payment Plans\n\n'
                'Reschedule active loans when borrowers fall behind.\n\n'
                '### Restructure types\n'
                '- `EXTEND_TERM` - spread balance over more installments\n'
                '- `REDUCE_AMOUNT` - smaller installments, same term\n'
                '- `MORATORIUM` - payment holiday for N days\n'
                '- `REFINANCE` - combine with new terms\n\n'
                '### Workflow\n'
                '`PROPOSED` -> `APPROVED` -> `APPLIED`\n'
                '(or `REJECTED` at the PROPOSED stage)\n\n'
                '### What happens on APPLY\n'
                '1. Old unpaid installments are removed\n'
                '2. New schedule is generated from the approved terms\n'
                '3. Loan balance and maturity are updated\n'
                '4. Penalties (if waived) generate a GL entry\n'
                '5. Every step is logged in `RestructureEvent`\n\n'
                '**Propose:** any branch staff. **Approve/Reject:** Branch Manager or HQ. **Apply:** HQ only.'
            ),
        },
                {
            'name': 'KYC - Requirements',
            'description': (
                '## KYC Document Requirements\n\n'
                'Configurable per client type + risk level.\n\n'
                '### Risk levels\n'
                '- `LOW` — minimal docs (NRC, photo)\n'
                '- `MEDIUM` — plus address proof, income proof\n'
                '- `HIGH` — plus bank statements, extra review\n'
                '- `PEP` — Enhanced Due Diligence required\n\n'
                '**FIC Zambia requires 10-year retention of all KYC records.**'
            ),
        },
        {
            'name': 'KYC - Verifications',
            'description': (
                '## KYC Verification Workflow\n\n'
                '### Status flow\n'
                '`NOT_STARTED` → `IN_PROGRESS` → `PENDING_REVIEW` → `VERIFIED`\n'
                '(or `REJECTED`, `EXPIRED`)\n\n'
                '### Actions\n'
                '- `POST .../initiate/` — start verification for a client\n'
                '- `POST .../run_checks/` — run automated ID/AML/PEP checks\n'
                '- `POST .../verify/` — mark as verified (manager+)\n'
                '- `POST .../reject/` — reject with reason\n'
                '- `GET  .../completion/` — see missing required documents\n\n'
                '**Providers:** Smile ID, VOVE ID, or manual fallback. '
                'Configured via `KYC.PROVIDER` in settings.'
            ),
        },
        {
            'name': 'KYC - Documents',
            'description': 'Uploaded KYC files with OCR extraction and verification status.',
        },
        {
            'name': 'KYC - Checks',
            'description': 'Individual check results: ID verification, OCR, face match, liveness, AML, PEP.',
        },
        {
            'name': 'KYC - Risk',
            'description': (
                '## Risk Assessments\n\n'
                'Computed from client data: age, location, occupation, PEP/sanctions hits.\n\n'
                'Levels: `LOW` `MEDIUM` `HIGH` `PEP`. Higher levels require more documents and more frequent re-review.'
            ),
        },
        {
            'name': 'KYC - Review Schedule',
            'description': 'Periodic re-verification reminders. High-risk clients reviewed yearly, low-risk every 3 years.',
        },
        {
            'name': 'KYC - Self Service',
            'description': (
                '## Client Self-Service KYC\n\n'
                'Generate a one-time token, send it to the client, and they can '
                'submit their KYC documents online without logging in.\n\n'
                '### Flow\n'
                '1. Staff calls `POST /api/kyc/self-service/generate_token/`\n'
                '2. Token link sent via SMS/WhatsApp\n'
                '3. Client opens link, uploads documents, submits\n'
                '4. Staff reviews and verifies'
            ),
        },
        {
            'name': 'Reports',
            'description': (
                '## Operational Reports\n\n'
                'Non-financial analytics for dashboards.\n\n'
                '- `GET /reports/dashboard/` - KPIs for caller\'s scope\n'
                '- `GET /reports/daily-collections/` - payments by branch\n'
                '- `GET /reports/loan-portfolio/` - breakdown by product\n'
                '- `GET /reports/branch-performance/` - HQ-only comparison'
            ),
        },
        {
            'name': 'Audit',
            'description': (
                '## System Activity Log\n\n'
                'Immutable audit trail of every write operation. Captures who, what, '
                'when, how (old/new JSON snapshots), and where from (IP).\n\n'
                '**Read-only** - records are written by the system, never modified.\n\n'
                'Essential for fraud investigations, regulatory inspections, and client '
                'dispute resolution.\n\n'
                'Filter by `action`, `entity_type`, `user`, or `branch`.'
            ),
        },
                {
            'name': 'Accounting - Bank Accounts',
            'description': (
                '## Bank Accounts\n\n'
                'Each bank account held by a branch. Links the physical bank account '
                'to the General Ledger account that mirrors it (typically `1020 Bank`).\n\n'
                '**Fields:** bank name, account number, currency, opening balance, '
                'and the linked GL account.\n\n'
                '**Only `HQ_ADMIN`** can create or edit bank accounts.'
            ),
        },
        {
            'name': 'Accounting - Bank Statements',
            'description': (
                '## Bank Statements\n\n'
                'A statement issued by the bank for a period. Each statement holds '
                'a list of transaction lines that must be matched against GL entries.\n\n'
                '### Workflow\n'
                '1. Create a statement with period + opening/closing balances\n'
                '2. Add or import statement lines\n'
                '3. `POST /accounting/bank-statements/{id}/auto_match/` — auto-match against GL\n'
                '4. Manually resolve any leftover unmatched lines\n'
                '5. `POST /accounting/bank-statements/{id}/reconcile/` — compute the report\n\n'
                '**Status flow:** `DRAFT` → `IN_PROGRESS` → `RECONCILED`'
            ),
        },
        {
            'name': 'Accounting - Bank Statement Lines',
            'description': (
                '## Bank Statement Lines\n\n'
                'Individual transactions on a bank statement. Each line can be matched '
                'to exactly one `JournalLine` on the linked bank GL account.\n\n'
                '### Match statuses\n'
                '- `UNMATCHED` — no journal entry found\n'
                '- `AUTO_MATCHED` — matched by the auto-match engine\n'
                '- `MANUAL_MATCHED` — confirmed by a user\n'
                '- `EXCLUDED` — deliberately ignored (e.g., informational lines)\n\n'
                '### Manual operations\n'
                '- `POST .../manual_match/` with `{"journal_line_id": N}`\n'
                '- `POST .../unmatch/` — clear the match\n'
                '- `POST .../exclude/` — exclude from reconciliation'
            ),
        },
        {
            'name': 'Accounting - Bank Reconciliations',
            'description': (
                '## Bank Reconciliations\n\n'
                'Immutable snapshots of a reconciliation session. Every time you run '
                '`POST /accounting/bank-statements/{id}/reconcile/`, a new snapshot is '
                'saved showing:\n\n'
                '- Statement opening/closing balances\n'
                '- GL opening/closing balances\n'
                '- Reconciled difference\n'
                '- `is_reconciled` flag (true when difference = 0)\n\n'
                '**Read-only** — created by the system on demand.'
            ),
        },
                {
            'name': 'Expenses',
            'description': (
                '## Operating Expenses\n\n'
                'Record and approve day-to-day costs: rent, salaries, fuel, '
                'utilities, bank charges, licenses.\n\n'
                '### Workflow\n'
                '`DRAFT` -> `SUBMITTED` -> `APPROVED` -> `PAID`\n'
                '(or `REJECTED` at the SUBMITTED stage)\n\n'
                '### GL posting\n'
                'When marked `PAID`, the system posts:\n'
                '- `DR <category expense account>`\n'
                '- `CR Cash / Bank / Mobile Money`\n\n'
                '### Approval rules\n'
                'Each category can require approval and set a threshold amount. '
                'Above the threshold, only `HQ_ADMIN` can approve.'
            ),
        },
        {
            'name': 'Expense Categories',
            'description': (
                '## Expense Categories\n\n'
                'Groups expenses by type and maps each to a GL account.\n\n'
                '**Standard categories seeded on onboarding:**\n'
                '- RENT  - Rent (5200 Operating Expenses)\n'
                '- SAL   - Salaries (5300 Salaries and Wages)\n'
                '- UTIL  - Utilities (5200)\n'
                '- FUEL  - Fuel and Transport (5200)\n'
                '- BANK  - Bank Charges (5200)\n'
                '- LIC   - Licenses and Fees (5200)\n'
                '- OFFC  - Office Supplies (5200)\n\n'
                '**Only `HQ_ADMIN`** can create or edit categories.'
            ),
        },
        
    ],
}

# ============================================================
# Notifications (SMS + WhatsApp)
# ============================================================
NOTIFICATIONS = {
    # 'console' | 'africastalking' | 'whatsapp_cloud'
    'PROVIDER': os.getenv('NOTIF_PROVIDER', 'console'),

    'AFRICASTALKING': {
        'USERNAME':  os.getenv('AT_USERNAME', ''),
        'API_KEY':   os.getenv('AT_API_KEY', ''),
        'SENDER_ID': os.getenv('AT_SENDER_ID', ''),
    },

    'WHATSAPP': {
        'PHONE_ID':     os.getenv('WA_PHONE_ID', ''),
        'ACCESS_TOKEN': os.getenv('WA_ACCESS_TOKEN', ''),
    },

    # Days before due date to send a reminder
    'DUE_REMINDER_DAYS_BEFORE': 3,

    # Days past due at which to send an overdue notice
    'OVERDUE_REMINDER_DAYS': [1, 7, 30],
}

# ============================================================
# Origination workflow policy
# ============================================================
ORIGINATION = {
    # True  → strict: submitter ≠ approver, creator ≠ first reviewer,
    #         no consecutive actions by the same user.
    # False → relaxed: only requires roles to match (small-team mode)
    'ENFORCE_SEGREGATION_OF_DUTIES': os.getenv('ORIGINATION_ENFORCE_SOD', 'True').lower() == 'true',

    # True  → require a separate approver even for the final stage
    'REQUIRE_DISTINCT_APPROVER': os.getenv('ORIGINATION_DISTINCT_APPROVER', 'True').lower() == 'true',
}

# ============================================================
# KYC / AML
# ============================================================
KYC = {
    'PROVIDER': os.getenv('KYC_PROVIDER', 'manual'),

    'SMILE_ID': {
        'API_KEY':    os.getenv('SMILE_ID_API_KEY', ''),
        'PARTNER_ID': os.getenv('SMILE_ID_PARTNER_ID', ''),
        'ENVIRONMENT': os.getenv('SMILE_ID_ENV', 'sandbox'),
    },

    'VOVE_ID': {
        'API_KEY': os.getenv('VOVE_ID_API_KEY', ''),
    },

    # How long a verified KYC stays valid before re-review (months)
    'REVIEW_FREQUENCY_MONTHS': {
        'LOW': 36,
        'MEDIUM': 24,
        'HIGH': 12,
        'PEP': 6,
    },

    # Documents expire after this many months (for those that expire)
    'DEFAULT_DOCUMENT_VALIDITY_MONTHS': 60,

    # KYC approval threshold — above this, HQ review required
    'HQ_REVIEW_THRESHOLD_AMOUNT': 50000,
}

CORS_ALLOW_ALL_ORIGINS = True 

# ============================================================
# Celery (optional - add later for scheduled tasks)
# ============================================================
# CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
# CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379')