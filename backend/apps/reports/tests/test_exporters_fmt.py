"""Tests for exporter formatter helpers (pure functions, fast)."""
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
