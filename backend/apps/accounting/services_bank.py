# apps/accounting/services_bank.py
"""
Bank reconciliation services — orchestration layer.

This module handles:
  - Transactional auto-matching (DB writes, status updates)
  - Reconciliation snapshot computation (GL vs statement)
  - The public API used by views_bank.py

The actual scoring primitives live in matching.py. This module never
reimplements them.
"""
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    BankStatement, BankStatementLine, JournalLine, GLAccount,
)
from .matching import (
    find_candidates,
    composite_score,
    AUTO_ACCEPT_THRESHOLD,
    REVIEW_THRESHOLD,
)


# ============================================================
# AutoMatchingService
# ============================================================
class AutoMatchingService:
    """
    Runs the auto-match engine across all unmatched lines on a statement.
    Delegates all scoring to matching.py; this class owns the DB writes.
    """

    @staticmethod
    @transaction.atomic
    def auto_match_statement(statement: BankStatement, user=None) -> dict:
        """
        Auto-match all UNMATCHED lines on a statement.
        Lines scoring >= AUTO_ACCEPT_THRESHOLD are persisted as matches.
        Returns {'matched': n, 'unmatched': m}.

        Uses select_for_update(skip_locked=True) so concurrent runs
        (e.g., two staff clicking "Auto-Match" simultaneously) cannot
        double-match the same line.
        """
        unmatched_qs = (
            statement.lines
            .filter(match_status='UNMATCHED')
            .select_for_update(skip_locked=True)
        )

        matched_count = 0
        for bank_line in unmatched_qs:
            candidates = find_candidates(bank_line, limit=1)
            if not candidates:
                continue

            score, jl = candidates[0]
            if score['total'] < AUTO_ACCEPT_THRESHOLD:
                continue

            bank_line.matched_journal_line = jl
            bank_line.match_status = 'AUTO_MATCHED'
            bank_line.match_score = Decimal(str(score['total']))
            bank_line.match_rule = 'auto-ref+amount+desc+date'
            bank_line.matched_at = timezone.now()
            bank_line.matched_by = user
            bank_line.save(update_fields=[
                'matched_journal_line', 'match_status', 'match_score',
                'match_rule', 'matched_at', 'matched_by',
            ])
            matched_count += 1

        # Refresh statement status based on remaining unmatched lines
        remaining = statement.lines.filter(match_status='UNMATCHED').count()
        if remaining == 0:
            new_status = 'RECONCILED'
        elif statement.lines.exclude(match_status='UNMATCHED').exists():
            new_status = 'IN_PROGRESS'
        else:
            new_status = statement.status

        if new_status != statement.status:
            statement.status = new_status
            statement.save(update_fields=['status'])

        return {'matched': matched_count, 'unmatched': remaining}

    @staticmethod
    def suggest_matches(bank_line: BankStatementLine, limit: int = 10) -> list:
        """
        Public API for the UI. Returns a JSON-friendly ranked list of
        candidates for a given bank line, without touching the database
        (read-only).
        """
        results = []
        for score, jl in find_candidates(bank_line, limit=limit):
            results.append({
                'journal_line_id': jl.id,
                'journal_entry_reference': jl.journal_entry.reference,
                'journal_entry_date': str(jl.journal_entry.entry_date),
                'description': jl.memo or jl.journal_entry.description[:80],
                'debit': str(jl.debit),
                'credit': str(jl.credit),
                'score': score['total'],
                'score_breakdown': score,
            })
        return results

    @staticmethod
    def score_pair(bank_line: BankStatementLine,
                   journal_line: JournalLine) -> dict:
        """
        Expose composite_score for callers (e.g., manual_match) that want
        to record the score for a manually-selected pair.
        """
        return composite_score(bank_line, journal_line)


# ============================================================
# ReconciliationService
# ============================================================
class ReconciliationService:
    """
    Computes the reconciliation snapshot for a statement:
      - statement opening / closing balance (from the imported file)
      - GL opening / closing balance (from posted journal lines)
      - reconciled difference
    """

    @staticmethod
    def _gl_balance_as_of(gl_account: GLAccount, as_of_date) -> Decimal:
        """
        Return the GL balance for a bank asset account as of a date.
        Bank asset is debit-normal: balance = sum(debit) - sum(credit).
        """
        agg = (
            JournalLine.objects
            .filter(
                account=gl_account,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
                journal_entry__entry_date__lte=as_of_date,
            )
            .aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit'),
            )
        )
        debit = agg['total_debit'] or Decimal('0')
        credit = agg['total_credit'] or Decimal('0')
        return debit - credit

    @staticmethod
    def compute(statement: BankStatement) -> dict:
        """
        Return the reconciliation snapshot. Read-only — does not persist.
        Persistence happens in views_bank.reconcile().
        """
        bank_account = statement.bank_account
        gl_account = bank_account.gl_account

        stmt_open  = Decimal(statement.opening_balance)
        stmt_close = Decimal(statement.closing_balance)

        gl_open  = ReconciliationService._gl_balance_as_of(
            gl_account, statement.period_from - timedelta(days=1),
        )
        gl_close = ReconciliationService._gl_balance_as_of(
            gl_account, statement.period_to,
        )

        difference = stmt_close - gl_close

        return {
            'statement_opening_balance': stmt_open,
            'statement_closing_balance': stmt_close,
            'gl_opening_balance': gl_open,
            'gl_closing_balance': gl_close,
            'difference': difference,
            'is_reconciled': abs(difference) < Decimal('0.01'),
            'unmatched_lines': statement.lines.filter(match_status='UNMATCHED').count(),
            'matched_lines': statement.lines.exclude(match_status='UNMATCHED').count(),
        }