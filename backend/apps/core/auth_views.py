from django.contrib.auth import authenticate, login as django_login
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.throttling import AnonRateThrottle


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Existing claims
        token['username'] = user.username
        token['role'] = user.role
        token['branch_id'] = str(user.branch_id) if user.branch_id else None
        token['branch_code'] = user.branch.code if user.branch else None

        # Multi-tenancy claims
        token['organization_id'] = str(user.organization_id) if user.organization_id else None
        token['organization_code'] = user.organization.code if user.organization else None
        token['is_platform_admin'] = bool(
            user.is_superuser or getattr(user, 'is_platform_admin', False)
        )

        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [AnonRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = authenticate(
                username=request.data.get("username"),
                password=request.data.get("password"),
            )
            if user is not None:
                django_login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
        return response