# apps/portal/urls.py
from django.urls import path
from . import views


urlpatterns = [
    path('login/', views.portal_login, name='portal-login'),
    path('logout/', views.portal_logout, name='portal-logout'),
    path('', views.dashboard, name='portal-dashboard'),
    path('loans/', views.loans_list, name='portal-loans-list'),
    path('loans/<uuid:pk>/', views.loan_detail, name='portal-loan-detail'),
    path('apply/', views.apply_new, name='portal-apply'),
    path('profile/', views.profile, name='portal-profile'),
    path('applications/', views.applications_list, name='portal-applications'),
    path('applications/<uuid:pk>/', views.application_detail, name='portal-application-detail'),
]