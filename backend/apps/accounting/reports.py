from datetime import date
from django.db.models import Sum, Count
from decimal import Decimal


class BoZReportGenerator:
    """Generates Bank of Zambia prudential returns for MFIs."""

    @staticmethod
    def npl_return(organization, as_of_date: date = None):
        """
        BoZ Non-Performing Loan (NPL) return.
        One row per loan with classification, DPD, outstanding, provision.
        """
        from .models import LoanLossProvision

        if as_of_date is None:
            as_of_date = date.today()

        provisions = (
            LoanLossProvision.objects
            .filter(loan__organization=organization, provision_date=as_of_date)
            .select_related('loan', 'loan__client', 'loan__branch', 'loan__loan_product')
            .order_by('loan__branch__code', 'loan__loan_number')
        )

        rows = []
        totals = {
            'outstanding': Decimal('0'),
            'provision': Decimal('0'),
            'npl_outstanding': Decimal('0'),
            'npl_provision': Decimal('0'),
        }

        for p in provisions:
            is_npl = p.classification in ('SUBSTANDARD', 'DOUBTFUL', 'LOSS')
            row = {
                'branch_code': p.loan.branch.code,
                'loan_number': p.loan.loan_number,
                'client_name': f"{p.loan.client.first_name} {p.loan.client.last_name}",
                'client_nrc': p.loan.client.nrc,
                'product_code': p.loan.loan_product.code,
                'outstanding_balance': float(p.outstanding_balance),
                'days_past_due': p.days_past_due,
                'classification': p.classification,
                'provision_rate': float(p.provision_rate),
                'provision_amount': float(p.provision_amount),
                'is_npl': is_npl,
            }
            rows.append(row)

            totals['outstanding'] += p.outstanding_balance
            totals['provision'] += p.provision_amount
            if is_npl:
                totals['npl_outstanding'] += p.outstanding_balance
                totals['npl_provision'] += p.provision_amount

        npl_ratio = (
            float(totals['npl_outstanding'] / totals['outstanding'] * 100)
            if totals['outstanding'] > 0 else 0.0
        )

        return {
            'organization': organization.code,
            'as_of_date': str(as_of_date),
            'rows': rows,
            'totals': {
                'total_outstanding': float(totals['outstanding']),
                'total_provision': float(totals['provision']),
                'npl_outstanding': float(totals['npl_outstanding']),
                'npl_provision': float(totals['npl_provision']),
                'npl_ratio_percent': round(npl_ratio, 2),
            },
            'classification_summary': BoZReportGenerator._classification_summary(provisions),
        }

    @staticmethod
    def _classification_summary(provisions):
        summary = {}
        for p in provisions:
            key = p.classification
            if key not in summary:
                summary[key] = {
                    'count': 0,
                    'outstanding': Decimal('0'),
                    'provision': Decimal('0'),
                }
            summary[key]['count'] += 1
            summary[key]['outstanding'] += p.outstanding_balance
            summary[key]['provision'] += p.provision_amount

        return {
            k: {
                'count': v['count'],
                'outstanding': float(v['outstanding']),
                'provision': float(v['provision']),
            }
            for k, v in summary.items()
        }

    @staticmethod
    def portfolio_at_risk(organization, as_of_date: date = None):
        """
        PAR 1, 7, 30, 60, 90 — the standard MFI risk ratios.
        """
        from .models import LoanLossProvision

        if as_of_date is None:
            as_of_date = date.today()

        provisions = LoanLossProvision.objects.filter(
            loan__organization=organization, provision_date=as_of_date,
        )

        total = provisions.aggregate(
            total_outstanding=Sum('outstanding_balance'),
        )['total_outstanding'] or Decimal('0')

        buckets = {
            'par_1': 1,
            'par_7': 7,
            'par_30': 30,
            'par_60': 60,
            'par_90': 90,
        }

        result = {'as_of_date': str(as_of_date), 'total_portfolio': float(total)}

        for label, days in buckets.items():
            overdue = provisions.filter(days_past_due__gte=days).aggregate(
                sum=Sum('outstanding_balance'),
            )['sum'] or Decimal('0')
            ratio = (overdue / total * 100) if total > 0 else Decimal('0')
            result[label] = {
                'overdue_balance': float(overdue),
                'ratio_percent': round(float(ratio), 2),
            }

        return result