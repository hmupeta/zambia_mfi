# apps/momo/urls_pages.py
from django.urls import path
from . import views_pages

urlpatterns = [
    # Disabled until views_pages.momo_dashboard is implemented.
    # path('momo/', views_pages.momo_dashboard, name='momo-dashboard-page'),

    path(
        'settings/mobile-money/',
        views_pages.mobile_money_settings_page,
        name='ui-settings-mobile-money',
    ),
]