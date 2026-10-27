from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import LoanRestructureViewSet

router = DefaultRouter()
router.register(r'', LoanRestructureViewSet, basename='loan-restructure')

urlpatterns = [
    path('', include(router.urls)),
]