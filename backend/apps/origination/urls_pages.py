# apps/origination/urls_pages.py
from django.urls import path
from . import views_pages


urlpatterns = [
    path('applications/', views_pages.applications_list, name='applications-list-page'),
    path('applications/new/', views_pages.application_new, name='applications-new-page'),
    path('applications/<uuid:pk>/', views_pages.application_detail, name='applications-detail-page'),
]