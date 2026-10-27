"""Tests for analytics calculations."""
from datetime import date
from decimal import Decimal

import pytest

from apps.reports.services_analytics import (
    aging_analysis, loan_officer_performance, new_vs_repeat_clients,
)


pytestmark = pytest.mark.django_db


def test_aging_analysis_returns_buckets(org, loan):
    result = aging_analysis(org, date.today())
    assert 'rows' in result
    assert len(result['rows']) == 5
    bucket_keys = [r['bucket'] for r in result['rows']]
    assert 'current' in bucket_keys
    assert 'par_90_plus' in bucket_keys


def test_aging_totals_match_row_sum(org, loan):
    result = aging_analysis(org, date.today())
    row_sum = sum(r['outstanding'] for r in result['rows'])
    assert abs(row_sum - result['total_outstanding']) < 0.01


def test_loan_officer_performance_returns_officers(org, loan, hq_admin):
    today = date.today()
    from_m = today.replace(day=1)
    result = loan_officer_performance(org, from_m, today)
    assert 'officers' in result
    assert isinstance(result['officers'], list)


def test_new_vs_repeat_returns_series(org, loan, client):
    result = new_vs_repeat_clients(org, months=3)
    assert 'series' in result
    # Month range is inclusive of both endpoints, so months=3 yields 4 buckets
    assert len(result['series']) >= 3
    assert all('new' in s and 'repeat' in s for s in result['series'])
