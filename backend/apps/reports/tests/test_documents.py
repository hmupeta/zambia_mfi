"""Tests for printable document helpers."""
from decimal import Decimal

import pytest

from apps.reports.documents import amount_in_words, _sanitize


def test_amount_in_words_zero():
    assert 'Zero' in amount_in_words(Decimal('0'))


def test_amount_in_words_whole_kwacha():
    result = amount_in_words(Decimal('1000'))
    assert 'One Thousand Kwacha' in result
    assert 'Only' in result


def test_amount_in_words_with_ngwee():
    result = amount_in_words(Decimal('1234.56'))
    assert 'One Thousand' in result
    assert 'Ngwee' in result


def test_amount_in_words_complex():
    result = amount_in_words(Decimal('10000'))
    assert 'Ten Thousand Kwacha' in result


def test_sanitize_handles_none():
    assert _sanitize(None) == ''


def test_sanitize_replaces_em_dash():
    assert '--' in _sanitize('Hello \u2014 World')


def test_sanitize_replaces_curly_quotes():
    out = _sanitize('\u2018Hello\u2019 \u201CWorld\u201D')
    assert "'Hello'" in out
    assert '"World"' in out
