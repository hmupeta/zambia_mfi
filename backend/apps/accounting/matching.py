# apps/accounting/matching.py
"""
Pure scoring primitives for bank reconciliation.

This module contains ONLY stateless functions. No database writes, no
side effects, no service orchestration. Everything here is safe to unit
test in isolation and to reuse from Celery tasks, management commands,
or API views.

Weights:
    reference (40%) + amount (35%) + description (15%) + date (10%)

Thresholds:
    AUTO_ACCEPT_THRESHOLD = 95   # auto-reconcile immediately
    REVIEW_THRESHOLD      = 80   # queue for human review
"""
from decimal import Decimal
from datetime import timedelta

from rapidfuzz import fuzz

from apps.accounting.models import BankStatementLine, JournalLine


# ============================================================
# Tunables
# ============================================================
WEIGHT_REFERENCE    = 40
WEIGHT_AMOUNT       = 35
WEIGHT_DESCRIPTION  = 15
WEIGHT_DATE         = 10

AUTO_ACCEPT_THRESHOLD = 95
REVIEW_THRESHOLD      = 80
DATE_TOLERANCE_DAYS   = 3


# ============================================================
# Scoring primitives
# ============================================================
def score_amount(bank_debit: Decimal, bank_credit: Decimal,
                 journal_debit: Decimal, journal_credit: Decimal) -> float:
    """
    Compare bank amount to journal amount using absolute values.
    Bank Dr = money in; Bank Cr = money out.
    Jnl Dr on a bank asset = money in; Jnl Cr = money out.
    We compare absolute magnitudes to keep the score sign-agnostic.
    """
    bank_amt = abs(Decimal(bank_debit) - Decimal(bank_credit))
    journal_amt = abs(Decimal(journal_debit) - Decimal(journal_credit))

    if bank_amt == journal_amt:
        return 100.0

    max_amt = max(bank_amt, journal_amt)
    if max_amt == 0:
        return 0.0

    diff_pct = abs(bank_amt - journal_amt) / max_amt
    if diff_pct <= Decimal('0.005'):
        return 95.0
    if diff_pct <= Decimal('0.01'):
        return 80.0
    if diff_pct <= Decimal('0.02'):
        return 60.0
    return 0.0


def score_reference(bank_ref: str, journal_ref: str) -> float:
    if not bank_ref or not journal_ref:
        return 0.0
    if bank_ref.strip().upper() == journal_ref.strip().upper():
        return 100.0
    return float(fuzz.token_sort_ratio(bank_ref, journal_ref))


def score_description(bank_desc: str, journal_memo: str) -> float:
    if not bank_desc or not journal_memo:
        return 0.0
    return float(fuzz.token_sort_ratio(bank_desc, journal_memo))


def score_date(bank_date, journal_date) -> float:
    if not bank_date or not journal_date:
        return 0.0
    delta = abs((bank_date - journal_date).days)
    if delta == 0:
        return 100.0
    if delta <= DATE_TOLERANCE_DAYS:
        return 80.0
    return 0.0


def composite_score(bank_line: BankStatementLine,
                    journal_line: JournalLine) -> dict:
    """Return the weighted composite score and its component breakdown."""
    ref_score  = score_reference(bank_line.reference,
                                 journal_line.journal_entry.reference)
    amt_score  = score_amount(bank_line.debit, bank_line.credit,
                              journal_line.debit, journal_line.credit)
    desc_score = score_description(bank_line.description, journal_line.memo)
    date_score = score_date(bank_line.transaction_date,
                            journal_line.journal_entry.entry_date)

    total = (
        ref_score  * WEIGHT_REFERENCE +
        amt_score  * WEIGHT_AMOUNT +
        desc_score * WEIGHT_DESCRIPTION +
        date_score * WEIGHT_DATE
    ) / 100.0

    return {
        'total':       round(total, 2),
        'reference':   round(ref_score, 2),
        'amount':      round(amt_score, 2),
        'description': round(desc_score, 2),
        'date':        round(date_score, 2),
    }


def find_candidates(bank_line: BankStatementLine, limit: int = 10) -> list:
    """
    Return the top N (score_dict, JournalLine) tuples for a bank line.
    Only considers JournalLines on the same bank GL account, within a
    +/- 15-day window, not yet matched, and posted.
    """
    gl_account = bank_line.statement.bank_account.gl_account
    start = bank_line.transaction_date - timedelta(days=15)
    end   = bank_line.transaction_date + timedelta(days=15)

    journal_lines = (
        JournalLine.objects
        .filter(
            account=gl_account,
            journal_entry__entry_date__range=(start, end),
            journal_entry__is_posted=True,
            journal_entry__is_reversed=False,
        )
        .exclude(statement_match__isnull=False)
        .select_related('journal_entry')
    )

    scored = []
    for jl in journal_lines:
        score = composite_score(bank_line, jl)
        if score['total'] >= REVIEW_THRESHOLD:
            scored.append((score, jl))

    scored.sort(key=lambda x: x[0]['total'], reverse=True)
    return scored[:limit]