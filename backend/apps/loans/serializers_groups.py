# apps/loans/serializers_groups.py
from rest_framework import serializers

from .models import (
    LoanGroup, LoanGroupMember, GroupMeeting, GroupAttendance, GroupCollection,
)
from apps.clients.models import Client


class GroupMemberSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_nrc = serializers.CharField(source='client.nrc', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    client_kyc = serializers.CharField(source='client.kyc_status', read_only=True)

    class Meta:
        model = LoanGroupMember
        fields = '__all__'
        read_only_fields = ['id', 'joined_at']

    def get_client_name(self, obj):
        return f'{obj.client.first_name} {obj.client.last_name}'.strip()


class GroupMeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupMeeting
        fields = '__all__'
        read_only_fields = ['id', 'meeting_number', 'created_at']


class GroupCollectionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source='created_by.get_full_name', read_only=True,
    )
    group_name = serializers.CharField(source='loan_group.group_name', read_only=True)
    group_code = serializers.CharField(source='loan_group.group_code', read_only=True)
    payment_count = serializers.SerializerMethodField()

    class Meta:
        model = GroupCollection
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'collection_number',
            'member_count', 'journal_entry', 'created_at',
        ]

    def get_payment_count(self, obj):
        return obj.payments.count()


class LoanGroupListSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    leader_name = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(read_only=True)
    portfolio = serializers.SerializerMethodField()

    class Meta:
        model = LoanGroup
        fields = [
            'id', 'group_name', 'group_code', 'branch', 'branch_code',
            'leader', 'leader_name', 'status', 'member_count',
            'cycle_number', 'meeting_frequency', 'meeting_day',
            'savings_balance', 'portfolio', 'created_at',
        ]

    def get_leader_name(self, obj):
        if not obj.leader:
            return ''
        return f'{obj.leader.first_name} {obj.leader.last_name}'.strip()

    def get_portfolio(self, obj):
        from django.db.models import Sum
        from .models import Loan
        agg = Loan.objects.filter(
            loan_group=obj, is_fully_repaid=False,
        ).aggregate(s=Sum('balance_due'))
        return float(agg['s'] or 0)


class LoanGroupDetailSerializer(LoanGroupListSerializer):
    members = GroupMemberSerializer(many=True, read_only=True)
    recent_meetings = serializers.SerializerMethodField()
    recent_collections = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta(LoanGroupListSerializer.Meta):
        fields = LoanGroupListSerializer.Meta.fields + [
            'notes', 'min_members', 'max_members',
            'cycle_start_date', 'cycle_end_date',
            'meeting_location', 'requires_cross_guarantee',
            'created_by', 'updated_at',
            'members', 'recent_meetings', 'recent_collections', 'summary',
        ]

    def get_recent_meetings(self, obj):
        qs = obj.meetings.order_by('-scheduled_date')[:5]
        return GroupMeetingSerializer(qs, many=True).data

    def get_recent_collections(self, obj):
        qs = obj.collections.order_by('-created_at')[:10]
        return GroupCollectionSerializer(qs, many=True).data

    def get_summary(self, obj):
        from .services_groups import GroupService
        return GroupService.group_summary(obj)


class CreateGroupSerializer(serializers.Serializer):
    group_name = serializers.CharField(max_length=100)
    branch = serializers.UUIDField()
    leader = serializers.UUIDField()
    meeting_frequency = serializers.ChoiceField(
        choices=['WEEKLY', 'BIWEEKLY', 'MONTHLY'], default='WEEKLY',
    )
    meeting_day = serializers.CharField(required=False, allow_blank=True, default='')
    meeting_location = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    min_members = serializers.IntegerField(default=5)
    max_members = serializers.IntegerField(default=30)


class RecordCollectionSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(
        choices=['CASH', 'BANK', 'MTN_MOMO', 'AIRTEL_MONEY'], default='CASH',
    )
    reference = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    meeting_id = serializers.UUIDField(required=False, allow_null=True)
    allocations = serializers.ListField(
        child=serializers.DictField(), allow_empty=False,
    )


class ScheduleMeetingSerializer(serializers.Serializer):
    scheduled_date = serializers.DateField()
    agenda = serializers.CharField(required=False, allow_blank=True, default='')


class RecordAttendanceSerializer(serializers.Serializer):
    member_ids = serializers.ListField(child=serializers.UUIDField())