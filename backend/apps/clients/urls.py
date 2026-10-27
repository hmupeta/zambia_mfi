from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ClientViewSet,
    ClientPaymentChannelViewSet,
    GuarantorViewSet,
    ClientDocumentViewSet,
)
from .views_admin import ClientAdminViewSet

router = DefaultRouter()
router.register(r'payment-channels', ClientPaymentChannelViewSet, basename='client-payment-channel')
router.register(r'guarantors', GuarantorViewSet, basename='guarantor')
router.register(r'documents', ClientDocumentViewSet, basename='client-document')
router.register(r'admin', ClientAdminViewSet, basename='client-admin')
router.register(r'', ClientViewSet, basename='client')

urlpatterns = [
    path('', include(router.urls)),
]