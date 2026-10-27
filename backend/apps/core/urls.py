# apps/core/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    OrganizationViewSet, BranchViewSet, UserViewSet, AuditLogViewSet,
    me, change_password, MeView,
)
from .auth_views import CustomTokenObtainPairView
from .views_settings import OrganizationSettingsViewSet, FeatureFlagViewSet
from .views_admin import UserAdminViewSet, BranchAdminViewSet


router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'audit-logs',    AuditLogViewSet,     basename='audit-log')
router.register(r'feature-flags', FeatureFlagViewSet,          basename='feature-flag')
router.register(r'branches',      BranchAdminViewSet,          basename='branch')
router.register(r'users',         UserAdminViewSet,            basename='user')


urlpatterns = [
    # ── JWT token endpoints ────────────────────────────────────
    # NOTE: your config/urls.py ALSO defines /api/auth/token/ directly,
    # so this CustomTokenObtainPairView is currently shadowed. If you
    # want the custom serializer at /api/auth/token/, either remove the
    # duplicate from config/urls.py or change one of the paths.
    path('token/',           CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/',   TokenRefreshView.as_view(),          name='token_refresh'),

    # ── Current user ───────────────────────────────────────────
    path('me/',              me,              name='api-me'),
        # Settings (Singleton — manually mapped so PATCH works on the base URL)
    path('settings/', OrganizationSettingsViewSet.as_view({
        'get': 'list',
        'post': 'create',
        'put': 'update',
        'patch': 'partial_update',
    }), name='organization-settings'),

    # ── Password change ────────────────────────────────────────
    path('change-password/', change_password, name='api-change-password'),

    # ── Router-generated endpoints ─────────────────────────────
    path('', include(router.urls)),
]