from django.urls import path
from .views_dashboard import executive_dashboard

from .views import (
    branch_dashboard,
    daily_collections_report,
    loan_portfolio_report,
    branch_performance, daily_trend,)

from .views_documents import (
    payment_receipt, client_statement,
    application_offer_letter, daily_collection_sheet,
)
from .views_analytics import (
    analytics_overview,
    analytics_loan_officers, analytics_aging,
    analytics_portfolio_movement, analytics_interest_income,
    analytics_new_vs_repeat,
)

urlpatterns = [
    path('dashboard/', branch_dashboard, name='branch-dashboard'),
    path('daily-collections/', daily_collections_report, name='daily-collections'),
    path('daily-trend/',        daily_trend),  
    path('loan-portfolio/', loan_portfolio_report, name='loan-portfolio'),
    path('branch-performance/', branch_performance, name='branch-performance'),
    # Executive dashboard on its own endpoint
    path('executive-dashboard/', executive_dashboard, name='executive-dashboard'),
    #Reports
    path('documents/receipt/<uuid:pk>/', payment_receipt, name='document-payment-receipt'),
    path('documents/statement/<uuid:pk>/', client_statement, name='document-client-statement'),
    path('documents/offer/<uuid:pk>/', application_offer_letter, name='document-offer-letter'),
    path('documents/daily-collection/', daily_collection_sheet, name='document-daily-collection'),
    #Advanced Analytics
    path('analytics/overview/', analytics_overview, name='analytics-overview'),
    path('analytics/loan-officers/', analytics_loan_officers, name='analytics-loan-officers'),
    path('analytics/aging/', analytics_aging, name='analytics-aging'),
    path('analytics/portfolio-movement/', analytics_portfolio_movement, name='analytics-portfolio-movement'),
    path('analytics/interest-income/', analytics_interest_income, name='analytics-interest-income'),
    path('analytics/new-vs-repeat/', analytics_new_vs_repeat, name='analytics-new-vs-repeat'),
]