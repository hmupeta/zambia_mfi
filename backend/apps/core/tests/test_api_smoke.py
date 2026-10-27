"""Smoke tests — endpoints reject unauthenticated requests."""
import pytest
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db


ENDPOINTS = [
    '/api/reports/dashboard/',
    '/api/reports/daily-trend/',
    '/api/reports/analytics/overview/',
    '/api/reports/analytics/aging/',
    '/api/reports/analytics/portfolio-movement/',
    '/api/reports/analytics/interest-income/',
    '/api/reports/analytics/new-vs-repeat/',
    '/api/reports/analytics/loan-officers/',
    '/api/payments/wallets/',
    '/api/payments/wallets/stats/',
    '/api/notifications/logs/',
    '/api/notifications/templates/',
    '/api/clients/',
    '/api/loans/admin/',
    '/api/origination/applications/',
]


@pytest.mark.parametrize('url', ENDPOINTS)
def test_endpoint_requires_auth(url):
    client = APIClient()
    r = client.get(url)
    assert r.status_code == 401, f'{url} returned {r.status_code}, expected 401'


@pytest.mark.parametrize('url', ENDPOINTS[:5])
def test_endpoint_returns_200_when_authed(url, auth_client):
    r = auth_client.get(url)
    assert r.status_code in (200, 201), f'{url} returned {r.status_code}'
