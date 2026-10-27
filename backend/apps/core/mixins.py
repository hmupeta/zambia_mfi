from .models import AuditLog
from rest_framework.utils.encoders import JSONEncoder
import json


class OrganizationScopedMixin:
    """
    Scope querysets to the user's organization.
    """
    org_field = 'organization'

    def get_queryset(self):
        # IMPORTANT: Do NOT call super().get_queryset() here.
        # Class-level `queryset = Model.objects.none()` (used for swagger
        # introspection) would permanently empty every response.
        # Instead, rebuild the queryset from the model each time.
        model = self.queryset.model
        qs = model.objects.all()

        # Swagger schema introspection - return empty so no data leaks
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()

        from .rbac import is_platform_admin, get_user_org_id

        # Platform admin (no org) sees everything
        if is_platform_admin(user) and not get_user_org_id(user):
            return qs

        org_id = get_user_org_id(user)
        if org_id is None:
            return qs.none()

        # Apply org filter
        if self.org_field == 'organization':
            return qs.filter(organization_id=org_id)
        return qs.filter(**{f'{self.org_field}_id': org_id})

    def get_create_kwargs(self):
        user = self.request.user
        org = getattr(user, 'organization', None)
        if org is not None and self.org_field == 'organization':
            if not self.request.data.get('organization'):
                return {'organization': org}
        return {}

    def get_create_kwargs(self):
        """
        Extra kwargs to pass to serializer.save() on create.
        Override in subclasses for custom logic.
        """
        user = self.request.user
        org = getattr(user, 'organization', None)

        if org is not None and self.org_field == 'organization':
            if not self.request.data.get('organization'):
                return {'organization': org}
        return {}


class AuditLogMixin:
    """Mixin to automatically log CRUD actions on viewsets."""

    def _get_audit_org(self, obj=None):
        if obj is not None:
            org = getattr(obj, 'organization', None)
            if org is not None:
                return org
        return getattr(self.request.user, 'organization', None)

    def _get_audit_branch(self, obj=None):
        if obj is not None:
            branch = getattr(obj, 'branch', None)
            if branch is not None:
                return branch
        return getattr(self.request.user, 'branch', None)

    def _json_safe(self, data):
        """
        Convert DRF serializer output into JSON-safe primitives.
        Handles UUID, Decimal, datetime, date, model instances, etc.
        """
        if data is None:
            return None
        try:
            return json.loads(json.dumps(data, cls=JSONEncoder))
        except (TypeError, ValueError):
            # Fallback: str() everything weird
            return json.loads(json.dumps(data, cls=JSONEncoder, default=str))

    def log_audit(self, action, entity_type, entity_id,
                  old_values=None, new_values=None, obj=None):
        AuditLog.objects.create(
            organization=self._get_audit_org(obj),
            user=self.request.user if self.request.user.is_authenticated else None,
            branch=self._get_audit_branch(obj),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=self._json_safe(old_values),
            new_values=self._json_safe(new_values),
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def _entity_name(self):
        return getattr(
            self, 'audit_entity_type',
            self.queryset.model.__name__ if hasattr(self, 'queryset') else 'Unknown',
        )

    def perform_create(self, serializer):
        kwargs = {}
        if hasattr(self, 'get_create_kwargs'):
            kwargs = self.get_create_kwargs()

        instance = serializer.save(**kwargs)

        self.log_audit(
            action='CREATE',
            entity_type=self._entity_name(),
            entity_id=instance.id,
            new_values=self.get_serializer(instance).data,
            obj=instance,
        )

    def perform_update(self, serializer):
        old = self.get_object()
        old_data = self.get_serializer(old).data
        instance = serializer.save()
        self.log_audit(
            action='UPDATE',
            entity_type=self._entity_name(),
            entity_id=instance.id,
            old_values=old_data,
            new_values=self.get_serializer(instance).data,
            obj=instance,
        )

    def perform_destroy(self, instance):
        old_data = self.get_serializer(instance).data
        entity_id = instance.id
        self.log_audit(
            action='DELETE',
            entity_type=self._entity_name(),
            entity_id=entity_id,
            old_values=old_data,
            obj=instance,
        )
        instance.delete()