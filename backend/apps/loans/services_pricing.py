"""
Loan pricing: interest calculation per method, and EIR derivation.

Interest methods supported:
  FLAT              — simple interest on principal for the whole term
  REDUCING_BALANCE  — interest on outstanding principal each period
  EQUAL_INSTALLMENT — EMI-style, reducing on original, amortized
  BALLOON           — interest-only during term, principal at maturity
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta


MONEY = Decimal('0.01')


def _periods_per_year(frequency):
    return {
        'DAILY': 365,
        'WEEKLY': 52,
        'BIWEEKLY': 26,
        'MONTHLY': 12,
    }.get(frequency, 12)


def _annual_rate(product):
    """Normalize the product's interest_rate to an annual decimal."""
    rate = Decimal(product.interest_rate or 0) / Decimal('100')
    if product.interest_rate_period == 'MONTHLY':
        return rate * 12
    return rate


def compute_eir(product):
    """
    Return annualized Effective Interest Rate as a percentage (2dp).
    EIR = the discount rate that makes NPV of all cash flows = 0.
    We compute it numerically to keep the code dependency-free.
    """
    principal, schedule = build_schedule(product, Decimal(product.min_amount or 0))
    if not schedule:
        return None

    # Cash flows: outflow at t=0 (principal), inflows at each installment
    # Time in years from t=0.
    flows = [(-principal, 0.0)]
    for inst in schedule:
        t_years = (inst['due_date'] - schedule[0]['due_date']).days / 365.0
        # Disbursement is typically 30d before first installment
        t_years += product.first_installment_grace_days / 365.0
        flows.append((inst['total_due'], t_years))

    # Bisection on annual discount rate
    def npv(r):
        total = Decimal('0')
        for amount, t in flows:
            total += Decimal(str(amount)) / (Decimal('1') + Decimal(str(r))) ** Decimal(str(t))
        return total

    lo, hi = Decimal('-0.9'), Decimal('10')  # -90% to 1000%
    for _ in range(80):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    eir = ((lo + hi) / 2) * 100
    return eir.quantize(MONEY, rounding=ROUND_HALF_UP)


def build_schedule(product, principal, start_date=None):
    """
    Return a list of dicts:
      { installment_no, due_date, principal, interest, fees, total_due }
    """
    principal = Decimal(str(principal))
    start_date = start_date or date.today()
    freq = product.repayment_frequency
    n = _num_installments(product, freq)
    if n <= 0:
        return []

    per_period_rate = _period_rate(product, freq)
    fee_total = sum(
        (f.compute(principal) for f in product.fees.filter(is_active=True)
         if f.charge_timing == 'ADD_FIRST_INSTALLMENT'),
        Decimal('0'),
    )

    schedule = []
    if product.interest_method == 'FLAT':
        total_interest = principal * per_period_rate * n
        per_inst_principal = (principal / n).quantize(MONEY, rounding=ROUND_HALF_UP)
        per_inst_interest = (total_interest / n).quantize(MONEY, rounding=ROUND_HALF_UP)
        for i in range(1, n + 1):
            due = _add_period(start_date, freq, i) + timedelta(days=product.first_installment_grace_days)
            schedule.append({
                'installment_no': i,
                'due_date': due,
                'principal': per_inst_principal,
                'interest': per_inst_interest,
                'fees': fee_total if i == 1 else Decimal('0'),
                'total_due': per_inst_principal + per_inst_interest + (fee_total if i == 1 else Decimal('0')),
            })

    elif product.interest_method in ('REDUCING_BALANCE', 'EQUAL_INSTALLMENT'):
        balance = principal
        per_inst_principal = (principal / n).quantize(MONEY, rounding=ROUND_HALF_UP)
        for i in range(1, n + 1):
            interest = (balance * per_period_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
            due = _add_period(start_date, freq, i) + timedelta(days=product.first_installment_grace_days)
            schedule.append({
                'installment_no': i,
                'due_date': due,
                'principal': per_inst_principal,
                'interest': interest,
                'fees': fee_total if i == 1 else Decimal('0'),
                'total_due': per_inst_principal + interest + (fee_total if i == 1 else Decimal('0')),
            })
            balance -= per_inst_principal

    elif product.interest_method == 'BALLOON':
        for i in range(1, n + 1):
            interest = (principal * per_period_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
            due = _add_period(start_date, freq, i) + timedelta(days=product.first_installment_grace_days)
            is_last = i == n
            schedule.append({
                'installment_no': i,
                'due_date': due,
                'principal': principal if is_last else Decimal('0'),
                'interest': interest,
                'fees': fee_total if i == 1 else Decimal('0'),
                'total_due': (principal if is_last else Decimal('0')) + interest + (fee_total if i == 1 else Decimal('0')),
            })

    return schedule


def _num_installments(product, freq):
    months = product.min_tenure_months or 0
    return {
        'DAILY': months * 30,
        'WEEKLY': months * 4,
        'BIWEEKLY': months * 2,
        'MONTHLY': months,
    }.get(freq, months)


def _period_rate(product, freq):
    annual = _annual_rate(product)
    return annual / _periods_per_year(freq)


def _add_period(start, freq, n):
    if freq == 'DAILY':
        return start + timedelta(days=n)
    if freq == 'WEEKLY':
        return start + timedelta(weeks=n)
    if freq == 'BIWEEKLY':
        return start + timedelta(weeks=2 * n)
    if freq == 'MONTHLY':
        month = start.month + n
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(start.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)
    return start