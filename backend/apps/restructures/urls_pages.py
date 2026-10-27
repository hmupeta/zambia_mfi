# apps/restructures/urls_pages.py
from django.urls import path
from . import views_pages

urlpatterns = [
    path('restructures/', views_pages.restructures_list, name='restructures-list-page'),
    path('restructures/<uuid:pk>/', views_pages.restructure_detail, name='restructure-detail-page'),
]