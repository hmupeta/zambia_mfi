#!/usr/bin/env python3
"""
Installer for Phase AE — additional test coverage for high-risk paths.
Run from backend/:   python install_coverage_bump.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

FILES = []
def add(path, content):
    FILES.append((path, content))

# ═════════════════════════════════════════════
# 1. Payment reversal — GL integrity
# ═════════════════════════════════════════════
add(ROOT / "apps" / "payments" / "tests" / "test_reversal_gl.py", r'''"""Tests for payment reversal — loan restoration and contra-JE posting."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.payments.services_admin import record_payment
from apps.accounting.models import JournalEntry


pytestmark = pytest.mark.django_db


def _reverse(api_client, payment_id, hq_admin, reason='Test reversal'):
    token = str(RefreshToken.for_user(hq_admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
    return api_client.post(
        f'/api/payments/admin/{payment_id}/reverse/',
        {'reason': reason},
        format='json',
    )


def test_reversal_restores_loan_balance(loan, hq_admin, gl_accounts, api_client):
    before = loan.balance_due
    payment, _ = record_payment(
        loan=loan, amount=Decimal('1000.00'), user=hq_admin,
        payment_method='CASH',
    )
    loan.refresh_from_db()
    assert loan.balance_due == before - Decimal('1000.00')

    r = _reverse(api_client, payment.id, hq_admin)
    assert r.status_code == 200, r.content

    loan.refresh_from_db()
    assert loan.balance_due == before


def test_reversal_creates_contra_je(loan, hq_admin, gl_accounts, api_client):
    payment, _ = record_payment(
        loan=loan, amount=Decimal('500.00'), user=hq_admin,
        payment_method='CASH',
    )
    original_je_id = payment.journal_entry_id
    assert original_je_id is not None

    je_count_before = JournalEntry.objects.count()
    r = _reverse(api_client, payment.id, hq_admin)
    assert r.status_code == 200

    # A new JE should have been created for the reversal
    assert JournalEntry.objects.count() == je_count_before + 1
    payment.refresh_from_db()
    assert payment.is_reversed is True


def test_reversal_unmarks_installments(loan, hq_admin, gl_accounts, api_client):
    inst = loan.installments.order_by('installment_no').first()
    payment, _ = record_payment(
        loan=loan, amount=inst.total_due, user=hq_admin,
        payment_method='CASH',
    )
    inst.refresh_from_db()
    assert inst.is_paid is True

    _reverse(api_client, payment.id, hq_admin)
    inst.refresh_from_db()
    assert inst.is_paid is False
    assert inst.status == 'PENDING'


def test_double_reversal_is_rejected(loan, hq_admin, gl_accounts, api_client):
    payment, _ = record_payment(
        loan=loan, amount=Decimal('100.00'), user=hq_admin,
        payment_method='CASH',
    )
    r1 = _reverse(api_client, payment.id, hq_admin)
    assert r1.status_code == 200

    r2 = _reverse(api_client, payment.id, hq_admin, reason='Again')
    assert r2.status_code == 400
    assert b'already reversed' in r2.content.lower()
''')

# ═════════════════════════════════════════════
# 2. The no-installments guard
# ═════════════════════════════════════════════
add(ROOT / "apps" / "payments" / "tests" / "test_no_installment_guard.py", r'''"""A payment against a loan with no installments must not crash the GL post."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.loans.models import Loan
from apps.payments.services_admin import record_payment


pytestmark = pytest.mark.django_db


def test_payment_with_no_installments_skips_gl(
    org, branch, client, loan_product, hq_admin, gl_accounts,
):
    loan = Loan.objects.create(
        organization=org, branch=branch, client=client, loan_product=loan_product,
        loan_number='LN-NOINST-0001',
        amount=Decimal('5000'), total_interest=Decimal('500'),
        total_amount_due=Decimal('5500'), disbursed_amount=Decimal('5000'),
        balance_due=Decimal('5500'),
        start_date=date.today(),
        maturity_date=date.today() + timedelta(days=180),
        interest_rate=Decimal('10'), interest_method='FLAT',
        repayment_frequency='MONTHLY', status='DISBURSED',
    )
    # Deliberately no installments created

    payment, total_allocated = record_payment(
        loan=loan, amount=Decimal('500'), user=hq_admin,
        payment_method='CASH',
    )

    # Should not raise, but should not have posted a JE either
    assert payment.journal_entry is None
    assert total_allocated == Decimal('0')
''')

# ═════════════════════════════════════════════
# 3. Accounting service — JE creation validation
# ═════════════════════════════════════════════
add(ROOT / "apps" / "accounting" / "tests" / "test_je_creation.py", r'''"""Tests for AccountingService.create_journal_entry validation."""
from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.services import AccountingService


pytestmark = pytest.mark.django_db


def test_create_balanced_je_succeeds(org, gl_accounts, hq_admin):
    je = AccountingService.create_journal_entry(
        organization=org,
        entry_date=date.today(),
        reference='TEST-JE-001',
        description='Test entry',
        lines=[
            {'account_code': '1010', 'debit': 100, 'credit': 0, 'memo': 'Debit'},
            {'account_code': '1100', 'debit': 0, 'credit': 100, 'memo': 'Credit'},
        ],
        source_type='Manual',
        source_id=None,
        user=hq_admin,
    )
    assert je is not None
    assert je.lines.count() == 2


def test_create_unbalanced_je_raises(org, gl_accounts, hq_admin):
    with pytest.raises(ValueError, match='[Uu]nbalanced'):
        AccountingService.create_journal_entry(
            organization=org,
            entry_date=date.today(),
            reference='TEST-JE-002',
            description='Unbalanced',
            lines=[
                {'account_code': '1010', 'debit': 100, 'credit': 0, 'memo': 'Only debit'},
            ],
            source_type='Manual',
            source_id=None,
            user=hq_admin,
        )


def test_je_lines_have_correct_accounts(org, gl_accounts, hq_admin):
    je = AccountingService.create_journal_entry(
        organization=org,
        entry_date=date.today(),
        reference='TEST-JE-003',
        description='Two-line JE',
        lines=[
            {'account_code': '1010', 'debit': 250, 'credit': 0, 'memo': ''},
            {'account_code': '4000', 'debit': 0, 'credit': 250, 'memo': ''},
        ],
        source_type='Manual',
        source_id=None,
        user=hq_admin,
    )
    codes = sorted(line.account.code for line in je.lines.all())
    assert codes == ['1010', '4000']
''')

# ═════════════════════════════════════════════
# 4. Exporter formatters — pure functions
# ═════════════════════════════════════════════
add(ROOT / "apps" / "reports" / "tests" / "test_exporters_fmt.py", r'''"""Tests for exporter formatter helpers (pure functions, fast)."""
from decimal import Decimal

from apps.reports.exporters import fmt_money, fmt_money_zero, _sanitize


# ---- fmt_money ----
def test_fmt_money_none():
    assert fmt_money(None) == '--'


def test_fmt_money_empty_string():
    assert fmt_money('') == '--'


def test_fmt_money_zero():
    assert fmt_money(0) == '--'


def test_fmt_money_positive():
    assert fmt_money(Decimal('1234.56')) == 'K1,234.56'


def test_fmt_money_negative():
    assert fmt_money(Decimal('-100')) == 'K-100.00'


def test_fmt_money_string_number():
    assert fmt_money('2500') == 'K2,500.00'


def test_fmt_money_large():
    assert fmt_money(Decimal('1234567.89')) == 'K1,234,567.89'


# ---- fmt_money_zero ----
def test_fmt_money_zero_zero_shows_kzero():
    assert fmt_money_zero(0) == 'K0.00'


def test_fmt_money_zero_none_shows_kzero():
    assert fmt_money_zero(None) == 'K0.00'


def test_fmt_money_zero_positive():
    assert fmt_money_zero(Decimal('1234.56')) == 'K1,234.56'


# ---- _sanitize ----
def test_sanitize_none():
    assert _sanitize(None) == ''


def test_sanitize_plain_ascii():
    assert _sanitize('hello') == 'hello'


def test_sanitize_em_dash():
    assert _sanitize('a\u2014b') == 'a--b'


def test_sanitize_curly_quote():
    assert _sanitize('\u2018hello\u2019') == "'hello'"


def test_sanitize_number():
    assert _sanitize(123) == '123'
''')

# ═════════════════════════════════════════════
# 5. Loan schedule invariants
# ═════════════════════════════════════════════
add(ROOT / "apps" / "loans" / "tests" / "test_loan_schedule.py", r'''"""Tests for loan schedule generation — invariants on the fixture loan."""
from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


def test_loan_has_expected_installment_count(loan):
    assert loan.installments.count() == 3


def test_installment_numbers_are_sequential(loan):
    numbers = list(
        loan.installments.order_by('installment_no')
        .values_list('installment_no', flat=True)
    )
    assert numbers == [1, 2, 3]


def test_installment_principal_sums_to_loan_principal(loan):
    total_principal = sum(
        (inst.principal_amount for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_principal - loan.amount) < Decimal('0.01')


def test_installment_interest_sums_to_total_interest(loan):
    total_interest = sum(
        (inst.interest_amount for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_interest - loan.total_interest) < Decimal('0.01')


def test_installment_total_due_matches_sum(loan):
    total_due = sum(
        (inst.total_due for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_due - loan.total_amount_due) < Decimal('0.01')


def test_installment_remaining_starts_equals_total_due(loan):
    """Fresh installments should have paid_amount=0, remaining=total_due."""
    for inst in loan.installments.all():
        assert inst.paid_amount == Decimal('0')
        assert inst.is_paid is False
        assert inst.status == 'PENDING'
''')

# ═════════════════════════════════════════════
# Write
# ═════════════════════════════════════════════
def main():
    print("Installing Phase AE test files...")
    for path, content in FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        print(f"  + {rel}")

    print(f"\nDone. {len(FILES)} files written.")
    print("\nNext steps:")
    print("  1. Apply the guard fix in apps/payments/services_admin.py")
    print("  2. python -m pytest apps/payments/tests/test_no_installment_guard.py -v")
    print("  3. python -m pytest -v")


if __name__ == "__main__":
    main()