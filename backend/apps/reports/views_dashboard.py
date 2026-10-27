# apps/reports/views_dashboard.py
from datetime import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status

from apps.core.permissions import IsAuthenticatedStaff
from .services_dashboard import DashboardService


@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def executive_dashboard(request):
    """
    GET /api/reports/executive-dashboard/?as_of=YYYY-MM-DD

    Returns a single JSON payload with all KPIs and chart series for the
    executive dashboard. Respects the user's organization scope.
    """
    # Resolve the user's organization — reload from DB because JWT-auth
    # backends sometimes return a lightweight user without FK relations.
    org = getattr(request.user, 'organization', None)
    if org is None:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.select_related('organization').get(pk=request.user.pk)
            org = user.organization
        except User.DoesNotExist:
            org = None

    if org is None:
        return Response(
            {'error': 'Your account is not linked to an organization.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    as_of_param = request.query_params.get('as_of')
    as_of = (
        datetime.strptime(as_of_param, '%Y-%m-%d').date()
        if as_of_param else None
    )

    data = DashboardService.full_dashboard(org, as_of)
    return Response(data)