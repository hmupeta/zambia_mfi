from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import (
    KYCDocumentRequirement, KYCVerification, KYCDocument, KYCCheck,
    KYCRiskAssessment, KYCReviewSchedule, KYCSelfServiceToken,
)


class KYCDocumentRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCDocumentRequirement
        fields = '__all__'
        read_only_fields = ['id', 'organization']


class KYCDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = KYCDocument
        fields = '__all__'
        read_only_fields = [
            'id', 'uploaded_at', 'uploaded_by', 'is_verified',
            'verified_by', 'verified_at', 'extracted_data',
        ]


class KYCCheckSerializer(serializers.ModelSerializer):
    check_type_display = serializers.CharField(source='get_check_type_display', read_only=True)

    class Meta:
        model = KYCCheck
        fields = '__all__'
        read_only_fields = ['id', 'checked_at']


class KYCRiskAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRiskAssessment
        fields = '__all__'
        read_only_fields = ['id', 'assessed_at']


class KYCVerificationSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_nrc = serializers.CharField(source='client.nrc', read_only=True)
    documents = KYCDocumentSerializer(many=True, read_only=True)
    checks = KYCCheckSerializer(many=True, read_only=True)
    risk_assessment = KYCRiskAssessmentSerializer(read_only=True)
    initiated_by_name = serializers.CharField(source='initiated_by.username', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.username', read_only=True)

    class Meta:
        model = KYCVerification
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'verification_number',
            'status', 'initiated_by', 'initiated_at', 'submitted_at',
            'reviewed_by', 'reviewed_at', 'verified_at', 'expires_at',
            'review_notes', 'rejection_reason',
        ]

    @extend_schema_field(serializers.CharField)
    def get_client_name(self, obj) -> str:
        return f'{obj.client.first_name} {obj.client.last_name}'


class KYCInitiateSerializer(serializers.Serializer):
    client = serializers.UUIDField()
    client_type = serializers.ChoiceField(
        choices=['INDIVIDUAL', 'BUSINESS', 'GROUP'], default='INDIVIDUAL',
    )


class KYCRunChecksSerializer(serializers.Serializer):
    id_type = serializers.ChoiceField(choices=['NRC', 'PASSPORT', 'DRIVERS_LICENSE', 'VOTER_ID'])
    id_number = serializers.CharField(max_length=30)
    full_name = serializers.CharField(max_length=200)
    dob = serializers.DateField(required=False, allow_null=True)
    # Added address so it matches the frontend modal
    address = serializers.CharField(required=False, allow_blank=True, default='') 


class KYCVerifySerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class KYCRejectSerializer(serializers.Serializer):
    reason = serializers.CharField()


class KYCReviewScheduleSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = KYCReviewSchedule
        fields = '__all__'

    @extend_schema_field(serializers.CharField)
    def get_client_name(self, obj) -> str:
        return f'{obj.client.first_name} {obj.client.last_name}'


class SelfServiceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCSelfServiceToken
        fields = ['id', 'token', 'expires_at', 'is_used', 'created_at']
        read_only_fields = fields


class SelfServiceSubmitSerializer(serializers.Serializer):
    token = serializers.CharField()
    id_type = serializers.ChoiceField(choices=['NRC', 'PASSPORT', 'DRIVERS_LICENSE', 'VOTER_ID'])
    id_number = serializers.CharField(max_length=30)
    full_name = serializers.CharField(max_length=200)
    dob = serializers.DateField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, default='')