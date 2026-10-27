# apps/payments/urls_wallet_pages.py
from django.urls import path
from . import views_wallet_pages

urlpatterns = [
    path('wallets/', views_wallet_pages.wallets_list, name='wallets-list-page'),
    path('wallets/<uuid:branch_id>/', views_wallet_pages.wallet_detail, name='wallet-detail-page'),
]