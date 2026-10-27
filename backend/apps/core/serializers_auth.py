# apps/core/serializers_auth.py

from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import LegalDocument, OrganizationAgreement


class NimbusTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer that:
      - Adds tenant/role claims to the JWT (so the frontend can build the menu
        without an extra round-trip).
      - Blocks login for users whose Organization is inactive (pending BoZ
        licence verification).
      - Emits a `needs_agreement` flag so the frontend redirects to
        /sign-agreement/ when there are unsigned active legal documents.
    """

    @classmethod
    def get_token(cls, user):
        """Embed custom claims into both access and refresh tokens."""
        token = super().get_token(user)

        token['username'] = user.username
        token['email'] = user.email
        token['role'] = user.role
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name

        if user.organization_id:
            token['organization_id'] = str(user.organization_id)
            token['organization_code'] = user.organization.code
            token['organization_name'] = user.organization.name

        if user.branch_id:
            token['branch_id'] = str(user.branch_id)
            token['branch_code'] = user.branch.code

        return token

    def validate(self, attrs):
        data = super().validate(attrs)   # runs username/password auth
        user = self.user

        # ── Org status check (skip platform admins) ────────────────
        if not getattr(user, 'is_platform_admin', False) and user.organization_id:
            if not user.organization.is_active:
                raise PermissionDenied(
                    detail=(
                        'Your account is pending verification of your Bank of '
                        'Zambia licence. You will be notified by email once '
                        'your organization has been activated.'
                    ),
                    code='ORG_PENDING_VERIFICATION',
                )

        # ── Agreement check ────────────────────────────────────────
        needs_agreement = False
        if not getattr(user, 'is_platform_admin', False) and user.organization_id:
            active_doc_ids = set(
                LegalDocument.objects.filter(is_active=True)
                .values_list('id', flat=True)
            )
            signed_doc_ids = set(
                OrganizationAgreement.objects
                .filter(organization=user.organization, status='SIGNED')
                .values_list('document_id', flat=True)
            )
            needs_agreement = bool(active_doc_ids - signed_doc_ids)

        data['needs_agreement'] = needs_agreement
        return data