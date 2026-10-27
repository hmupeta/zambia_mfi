# apps/loans/views_groups.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin

from .models import LoanGroup, LoanGroupMember, GroupMeeting, GroupCollection
from .serializers_groups import (
    LoanGroupListSerializer, LoanGroupDetailSerializer,
    GroupMemberSerializer, GroupMeetingSerializer, GroupCollectionSerializer,
    CreateGroupSerializer, RecordCollectionSerializer,
    ScheduleMeetingSerializer, RecordAttendanceSerializer,
)
from .services_groups import GroupService


class LoanGroupViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = LoanGroup.objects.none()
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'branch', 'meeting_frequency']
    search_fields = ['group_name', 'group_code', 'leader__first_name', 'leader__last_name']
    ordering_fields = ['created_at', 'group_name', 'savings_balance']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('branch', 'leader').prefetch_related('members')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LoanGroupDetailSerializer
        if self.action == 'create':
            return CreateGroupSerializer
        return LoanGroupListSerializer

    def create(self, request, *args, **kwargs):
        s = CreateGroupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        from apps.core.models import Branch
        from apps.clients.models import Client
        try:
            branch = Branch.objects.get(id=d['branch'], organization=request.user.organization)
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found.'}, status=404)
        try:
            leader = Client.objects.get(id=d['leader'], organization=request.user.organization)
        except Client.DoesNotExist:
            return Response({'error': 'Leader client not found.'}, status=404)

        try:
            group = GroupService.create_group(
                org=request.user.organization,
                branch=branch,
                name=d['group_name'],
                leader_client=leader,
                user=request.user,
                meeting_frequency=d['meeting_frequency'],
                meeting_day=d.get('meeting_day', ''),
                meeting_location=d.get('meeting_location', ''),
                notes=d.get('notes', ''),
                min_members=d['min_members'],
                max_members=d['max_members'],
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(
            LoanGroupDetailSerializer(group).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        group = self.get_object()
        client_id = request.data.get('client')
        role = request.data.get('role', 'MEMBER')
        if not client_id:
            return Response({'error': 'client is required.'}, status=400)

        from apps.clients.models import Client
        try:
            client = Client.objects.get(id=client_id, organization=group.organization)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found.'}, status=404)

        try:
            member = GroupService.add_member(group, client, request.user, role=role)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(GroupMemberSerializer(member).data, status=201)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        group = self.get_object()
        client_id = request.data.get('client')
        reason = request.data.get('reason', '')
        try:
            from apps.clients.models import Client
            client = Client.objects.get(id=client_id, organization=group.organization)
            GroupService.remove_member(group, client, request.user, reason=reason)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def start_cycle(self, request, pk=None):
        group = self.get_object()
        duration = int(request.data.get('duration_months', 12))
        try:
            GroupService.start_cycle(group, request.user, duration_months=duration)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        return Response(LoanGroupDetailSerializer(group).data)

    @action(detail=True, methods=['post'])
    def close_cycle(self, request, pk=None):
        group = self.get_object()
        try:
            GroupService.close_cycle(group, request.user, notes=request.data.get('notes', ''))
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        return Response(LoanGroupDetailSerializer(group).data)

    @action(detail=True, methods=['post'])
    def record_collection(self, request, pk=None):
        group = self.get_object()
        s = RecordCollectionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        meeting = None
        if d.get('meeting_id'):
            meeting = group.meetings.filter(id=d['meeting_id']).first()

        try:
            collection = GroupService.record_collection(
                group=group,
                collections_data=d['allocations'],
                user=request.user,
                channel=d['channel'],
                reference=d['reference'],
                notes=d['notes'],
                meeting=meeting,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(GroupCollectionSerializer(collection).data, status=201)

    # --- NEW SAVINGS ENDPOINT ---
    @action(detail=True, methods=['post'])
    def record_savings(self, request, pk=None):
        group = self.get_object()
        
        allocations = request.data.get('allocations', [])
        channel = request.data.get('channel', 'CASH')
        reference = request.data.get('reference', '')

        if not allocations:
            return Response({'error': 'No savings allocations provided.'}, status=400)

        try:
            total = GroupService.record_savings(
                group=group,
                savings_data=allocations,
                user=request.user,
                channel=channel,
                reference=reference
            )
        except Exception as e:
            return Response({'error': str(e)}, status=400)

        return Response({
            'status': 'Savings recorded successfully.',
            'total_saved': float(total) if total else 0
        }, status=201)
    # ----------------------------

    @action(detail=True, methods=['post'])
    def schedule_meeting(self, request, pk=None):
        group = self.get_object()
        s = ScheduleMeetingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        meeting = GroupService.schedule_meeting(
            group, s.validated_data['scheduled_date'],
            user=request.user, agenda=s.validated_data.get('agenda', ''),
        )
        return Response(GroupMeetingSerializer(meeting).data, status=201)

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        group = self.get_object()
        return Response(GroupService.group_summary(group))


class GroupMeetingViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = GroupMeeting.objects.none()
    serializer_class = GroupMeetingSerializer
    org_field = 'loan_group__organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['loan_group', 'status']
    ordering_fields = ['scheduled_date']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('loan_group')

    @action(detail=True, methods=['post'])
    def record_attendance(self, request, pk=None):
        meeting = self.get_object()
        s = RecordAttendanceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        GroupService.record_attendance(
            meeting, s.validated_data['member_ids'], request.user,
        )
        return Response(GroupMeetingSerializer(meeting).data)


class GroupCollectionViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = GroupCollection.objects.none()
    serializer_class = GroupCollectionSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['loan_group', 'channel']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('loan_group', 'created_by', 'meeting')