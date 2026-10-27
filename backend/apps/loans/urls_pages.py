# apps/loans/urls_pages.py
from django.urls import path

from . import views_pages
from . import views_admin


urlpatterns = [
    # Groups
    path('groups/', views_pages.groups_list, name='groups-list-page'),
    path('groups/<uuid:pk>/', views_pages.group_detail, name='group-detail-page'),

    # Loan restructure
    path('loans/<uuid:pk>/restructure/', views_pages.loan_restructure, name='loan-restructure-page'),

    # Loan products (mounted under /app/loans/products/ because this
    # module is included at /app/)
    path('loans/products/', views_admin.loan_products_list, name='ui-loan-products-list'),
    path('loans/products/new/', views_admin.loan_product_new, name='ui-loan-products-new'),
    path('loans/products/<uuid:pk>/', views_admin.loan_product_detail, name='ui-loan-products-detail'),
    path('loans/products/<uuid:pk>/edit/', views_admin.loan_product_edit, name='ui-loan-products-edit'),
    #Collection
    path('loans/collections/', views_admin.collections_dashboard, name='ui-collections-dashboard'),
]