from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationConfigViewSet, NotificationTemplateViewSet,
    NotificationLogViewSet, NotificationSendViewSet,
)

router = DefaultRouter()
router.register(r'config', NotificationConfigViewSet, basename='notification-config')
router.register(r'templates', NotificationTemplateViewSet, basename='notification-template')
router.register(r'logs', NotificationLogViewSet, basename='notification-log')
router.register(r'send', NotificationSendViewSet, basename='notification-send')

urlpatterns = [path('', include(router.urls))]
