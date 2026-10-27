"""Tests for AccountingService.create_journal_entry validation."""
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
