# apps/reports/services_dashboard.py
"""
Dashboard KPI computation.

All methods take `org` explicitly as the first argument — no thread-locals.
Returns plain dicts suitable for JSON serialization.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone


# ============================================================
# Field-name configuration — adjust if your Loan model differs
# ============================================================
LOAN_STATUS_FIELD      = 'status'
LOAN_STATUS_ACTIVE     = ('ACTIVE', 'DISBURSED', 'CURRENT', 'IN_ARREARS', 'active', 'disbursed')
LOAN_AMOUNT_FIELD      = 'principal'
LOAN_OUTSTANDING_FIELD = 'outstanding_balance'
LOAN_DISBURSED_FIELD   = 'disbursement_date'
LOAN_DPD_FIELD         = 'days_past_due'


# ============================================================
# Date helpers
# ============================================================
def _month_start(d):
    return d.replace(day=1)


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)


def _last_n_months(n, anchor=None):
    anchor = anchor or timezone.now().date()
    return [_add_months(_month_start(anchor), i) for i in range(-(n - 1), 1)]


# ============================================================
# Service
# ============================================================
class DashboardService:

    @staticmethod
    def kpis(org, as_of=None):
        from apps.loans.models import Loan
        from apps.clients.models import Client
        from apps.accounting.models import BankAccount, JournalLine
        from apps.payments.models import Payment

        as_of = as_of or timezone.now().date()

        active_loans = Loan.objects.filter(
            organization=org,
            **{f'{LOAN_STATUS_FIELD}__in': LOAN_STATUS_ACTIVE},
        )

        portfolio_total = active_loans.aggregate(
            total=Sum(LOAN_OUTSTANDING_FIELD)
        )['total'] or Decimal('0')

        active_loan_count = active_loans.count()

        par30_qs = active_loans.filter(**{f'{LOAN_DPD_FIELD}__gte': 30})
        par30_amount = par30_qs.aggregate(
            total=Sum(LOAN_OUTSTANDING_FIELD)
        )['total'] or Decimal('0')

        par30_pct = (
            float(par30_amount) / float(portfolio_total) * 100
            if portfolio_total else 0.0
        )

        try:
            active_clients = Client.objects.filter(organization=org, is_active=True).count()
        except Exception:
            active_clients = Client.objects.filter(organization=org).count()

        # Cash position — sum of journal lines on bank GL accounts
        bank_gl_ids = list(
            BankAccount.objects.filter(organization=org, is_active=True)
            .values_list('gl_account_id', flat=True)
        )
        cash_qs = JournalLine.objects.filter(
            account_id__in=bank_gl_ids,
            journal_entry__is_posted=True,
            journal_entry__is_reversed=False,
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        cash_position = (cash_qs['dr'] or Decimal('0')) - (cash_qs['cr'] or Decimal('0'))

        avg_loan = active_loans.aggregate(avg=Avg(LOAN_OUTSTANDING_FIELD))['avg'] or Decimal('0')
        
        # Today's collections
        today_collections = Payment.objects.filter(
            organization=org,
            received_at__date=as_of,
            is_reversed=False
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

        return {
            'portfolio_total': float(portfolio_total),
            'active_loans': active_loan_count,
            'par30_percent': round(par30_pct, 2),
            'par30_amount': float(par30_amount),
            'overdue_loans': par30_qs.count(),
            'active_clients': active_clients,
            'cash_position': float(cash_position),
            'avg_loan_size': float(avg_loan),
            'today_collections': float(today_collections),
        }

    @staticmethod
    def portfolio_trend(org, months=12):
        from apps.loans.models import Loan

        end = timezone.now().date()
        buckets = _last_n_months(months, end)
        result = []
        for m_start in buckets:
            m_end = _add_months(m_start, 1) - timedelta(days=1)
            qs = Loan.objects.filter(
                organization=org,
                **{
                    f'{LOAN_STATUS_FIELD}__in': LOAN_STATUS_ACTIVE,
                    f'{LOAN_DISBURSED_FIELD}__lte': m_end,
                },
            )
            total = qs.aggregate(total=Sum(LOAN_OUTSTANDING_FIELD))['total'] or Decimal('0')
            result.append({
                'month': m_start.strftime('%Y-%m'),
                'label': m_start.strftime('%b %y'),
                'value': float(total),
            })
        return result

    @staticmethod
    def par_aging(org):
        from apps.loans.models import Loan

        qs = Loan.objects.filter(
            organization=org,
            **{f'{LOAN_STATUS_FIELD}__in': LOAN_STATUS_ACTIVE},
        )

        buckets = [
            ('1-30',  1,  30),
            ('31-60', 31, 60),
            ('61-90', 61, 90),
            ('90+',   91, 99999),
        ]
        result = []
        for label, lo, hi in buckets:
            q = qs.filter(**{f'{LOAN_DPD_FIELD}__gte': lo, f'{LOAN_DPD_FIELD}__lte': hi})
            agg = q.aggregate(count=Count('id'), amount=Sum(LOAN_OUTSTANDING_FIELD))
            result.append({
                'bucket': label,
                'count': agg['count'] or 0,
                'amount': float(agg['amount'] or 0),
            })
        return result

    # --- NEW METHOD FOR EXECUTIVE DASHBOARD ---
    @staticmethod
    def par_aging_dict(org):
        """Returns PAR aging in a simple dict format for the frontend charts."""
        from apps.loans.models import Loan
        qs = Loan.objects.filter(
            organization=org,
            **{f'{LOAN_STATUS_FIELD}__in': LOAN_STATUS_ACTIVE},
        )
        buckets = {
            'par_1_30': (1, 30),
            'par_31_60': (31, 60),
            'par_61_90': (61, 90),
            'par_90_plus': (91, 99999),
        }
        result = {}
        for key, (lo, hi) in buckets.items():
            q = qs.filter(**{f'{LOAN_DPD_FIELD}__gte': lo, f'{LOAN_DPD_FIELD}__lte': hi})
            agg = q.aggregate(amount=Sum(LOAN_OUTSTANDING_FIELD))
            result[key] = float(agg['amount'] or 0)
        return result

    # --- NEW METHOD FOR EXECUTIVE DASHBOARD ---
    @staticmethod
    def savings_vs_loans(org):
        """Compares outstanding loan portfolio against group savings pool."""
        from apps.loans.models import Loan, LoanGroup
        
        loans_qs = Loan.objects.filter(
            organization=org,
            **{f'{LOAN_STATUS_FIELD}__in': LOAN_STATUS_ACTIVE},
        )
        loans_total = loans_qs.aggregate(total=Sum(LOAN_OUTSTANDING_FIELD))['total'] or Decimal('0')
        
        savings_total = LoanGroup.objects.filter(organization=org).aggregate(
            s=Sum('savings_balance')
        )['s'] or Decimal('0')
        
        return {
            'loans': float(loans_total),
            'savings': float(savings_total)
        }

    # --- NEW METHOD FOR EXECUTIVE DASHBOARD ---
    @staticmethod
    def kyc_stats(org):
        """Calculates KYC compliance rates."""
        from apps.clients.models import Client
        
        total_clients = Client.objects.filter(organization=org).count()
        verified = Client.objects.filter(organization=org, kyc_status='VERIFIED').count()
        
        return {
            'verified': verified,
            'unverified': total_clients - verified,
            'compliance_rate': (verified / total_clients * 100) if total_clients else 0
        }

    @staticmethod
    def income_expense_trend(org, months=6):
        from apps.accounting.models import JournalLine

        end = timezone.now().date()
        start = _add_months(_month_start(end), -(months - 1))

        lines = (
            JournalLine.objects
            .filter(
                account__organization=org,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
                journal_entry__entry_date__gte=start,
            )
            .annotate(month=TruncMonth('journal_entry__entry_date'))
            .values('month', 'account__account_type')
            .annotate(total_debit=Sum('debit'), total_credit=Sum('credit'))
        )

        by_month = {}
        for row in lines:
            if not row['month']:
                continue
            key = row['month'].strftime('%Y-%m')
            if key not in by_month:
                by_month[key] = {'income': 0.0, 'expense': 0.0}
            dr = float(row['total_debit'] or 0)
            cr = float(row['total_credit'] or 0)
            if row['account__account_type'] == 'INCOME':
                by_month[key]['income'] += (cr - dr)
            elif row['account__account_type'] == 'EXPENSE':
                by_month[key]['expense'] += (dr - cr)

        result = []
        for m_start in _last_n_months(months, end):
            key = m_start.strftime('%Y-%m')
            row = by_month.get(key, {'income': 0.0, 'expense': 0.0})
            result.append({
                'month': key,
                'label': m_start.strftime('%b %y'),
                'income': round(row['income'], 2),
                'expense': round(row['expense'], 2),
            })
        return result

    @staticmethod
    def disbursement_trend(org, months=6):
        from apps.loans.models import Loan

        end = timezone.now().date()
        start = _add_months(_month_start(end), -(months - 1))

        rows = (
            Loan.objects
            .filter(
                organization=org,
                **{f'{LOAN_DISBURSED_FIELD}__gte': start},
            )
            .annotate(month=TruncMonth(LOAN_DISBURSED_FIELD))
            .values('month')
            .annotate(count=Count('id'), amount=Sum(LOAN_AMOUNT_FIELD))
        )

        by_month = {r['month'].strftime('%Y-%m'): r for r in rows if r['month']}

        result = []
        for m_start in _last_n_months(months, end):
            key = m_start.strftime('%Y-%m')
            r = by_month.get(key)
            result.append({
                'month': key,
                'label': m_start.strftime('%b %y'),
                'count': r['count'] if r else 0,
                'amount': float(r['amount'] or 0) if r else 0.0,
            })
        return result

    @staticmethod
    def recent_activity(org, limit=8):
        from apps.accounting.models import JournalEntry

        qs = (
            JournalEntry.objects
            .filter(organization=org, is_posted=True)
            .order_by('-entry_date', '-created_at')[:limit]
        )
        return [
            {
                'date': str(je.entry_date),
                'reference': je.reference,
                'description': (je.description or '')[:80],
                'source_type': je.source_type,
                'is_reversed': je.is_reversed,
            }
            for je in qs
        ]

    @staticmethod
    def full_dashboard(org, as_of=None):
        as_of = as_of or timezone.now().date()

        def safe(fn, *args, default=None):
            try:
                return fn(*args)
            except Exception as e:
                import traceback
                print(f"[DashboardService] {fn.__name__} failed: {e}")
                traceback.print_exc()
                return default if default is not None else []

        kpis_data = safe(DashboardService.kpis, org, as_of, default={})
        
        # Build flattened structure for the new frontend charts
        flat_stats = {
            'total_clients': kpis_data.get('active_clients', 0),
            'active_loans': kpis_data.get('active_loans', 0),
            'total_disbursed': kpis_data.get('portfolio_total', 0.0),
            'par_30': kpis_data.get('par30_percent', 0.0),
            'overdue_loans': kpis_data.get('overdue_loans', 0),
            'today_collections': kpis_data.get('today_collections', 0.0),
            'new_clients_this_month': 0,
            'par_aging': safe(DashboardService.par_aging_dict, org, default={}),
            'savings_vs_loans': safe(DashboardService.savings_vs_loans, org, default={}),
            'kyc_stats': safe(DashboardService.kyc_stats, org, default={})
        }

        return {
            'as_of': str(as_of),
            **flat_stats, # Merges the new keys directly into the root JSON
            'kpis': kpis_data, # Keeps old structure intact
            'portfolio_trend':      safe(DashboardService.portfolio_trend, org, 12),
            'par_aging':            safe(DashboardService.par_aging, org), # Keeps old list format intact
            'income_expense_trend': safe(DashboardService.income_expense_trend, org, 6),
            'disbursement_trend':   safe(DashboardService.disbursement_trend, org, 6),
            'recent_activity':      safe(DashboardService.recent_activity, org, 8),
        }