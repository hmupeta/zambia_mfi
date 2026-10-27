from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import (
    WorkflowTemplate, WorkflowStage,
    LoanApplication, ApplicationDocument, ApplicationTransition, ApplicationReview,
    Task, TaskComment, Guarantor,  # Added Guarantor
)

# --- ADDED IMPORTS FOR CUSTOMER APP ---
from apps.loans.models import Loan 
from apps.payments.models import Payment # Adjust if Payment is in a different app
# --------------------------------------
from drf_spectacular.utils import extend_schema_serializer

class WorkflowStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStage
        fields = '__all__'
        read_only_fields = ['id']


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    stages = WorkflowStageSerializer(many=True, read_only=True)
    loan_product_code = serializers.CharField(source='loan_product.code', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = WorkflowTemplate
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at']


class ApplicationDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationDocument
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by']


class ApplicationTransitionSerializer(serializers.ModelSerializer):
    from_stage_name = serializers.CharField(source='from_stage.name', read_only=True)
    to_stage_name = serializers.CharField(source='to_stage.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ApplicationTransition
        fields = ['id', 'from_stage', 'from_stage_name', 'to_stage', 'to_stage_name',
                  'action', 'user', 'username', 'comments', 'created_at']
        read_only_fields = fields


class ApplicationReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='reviewer.username', read_only=True)
    stage_name = serializers.CharField(source='stage.name', read_only=True)

    class Meta:
        model = ApplicationReview
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'reviewer']


# ============================================================
# Guarantor Serializer
# ============================================================

@extend_schema_serializer(component_name="OriginationGuarantorSerializer")
class GuarantorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guarantor
        fields = ['id', 'full_name', 'phone_number', 'nrc', 'relationship']
        read_only_fields = ['id']


class LoanApplicationSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    product_name = serializers.CharField(source='loan_product.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    loan_officer_name = serializers.CharField(source='loan_officer.username', read_only=True)
    documents = ApplicationDocumentSerializer(many=True, read_only=True)
    transitions = ApplicationTransitionSerializer(many=True, read_only=True)
    reviews = ApplicationReviewSerializer(many=True, read_only=True)
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    
    # Added nested guarantors
    guarantors = GuarantorSerializer(many=True, read_only=True)

    # ---- Action permission fields (new) ----
    can_current_user_act = serializers.SerializerMethodField()
    action_block_reason = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'application_number', 'status',
            'workflow_template', 'current_stage',
            'credit_score', 'credit_score_grade',
            'submitted_by', 'submitted_at',
            'decided_by', 'decided_at', 'decision_notes',
            'loan', 'created_by', 'created_at', 'updated_at',
            # Action permission fields are read-only
            'can_current_user_act', 'action_block_reason',
        ]

    @extend_schema_field(serializers.CharField)
    def get_client_name(self, obj) -> str:
        return f'{obj.client.first_name} {obj.client.last_name}'

    @extend_schema_field(serializers.BooleanField)
    def get_can_current_user_act(self, obj) -> bool:
        """
        True when the current user is authorized to advance this application
        at its current stage — considering role AND segregation of duties.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False

        user = request.user
        stage = obj.current_stage

        # No active stage → nothing to act on
        if not stage:
            return False

        # Only allowed on active applications
        if obj.status not in ('SUBMITTED', 'UNDER_REVIEW'):
            return False

        # Role check
        if (
            user.role != stage.role_required
            and user.role != 'HQ_ADMIN'
            and not user.is_superuser
        ):
            return False

        # Segregation of duties — Rule 1: submitter cannot approve
        if stage.is_final and obj.submitted_by_id == user.id:
            return False

        # Segregation of duties — Rule 2: creator cannot review at Stage 1
        if stage.order == 1 and obj.created_by_id == user.id:
            return False

        # Segregation of duties — Rule 3: no consecutive actions
        last = obj.transitions.order_by('-created_at').first()
        if last and last.user_id == user.id:
            return False

        return True

    @extend_schema_field(serializers.CharField)
    def get_action_block_reason(self, obj) -> str:
        """
        Human-readable reason the current user cannot act. Empty when
        they can act. Useful for tooltips and disabled-button hints.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'Not authenticated.'

        user = request.user
        stage = obj.current_stage

        if not stage:
            return 'No active stage.'

        if obj.status not in ('SUBMITTED', 'UNDER_REVIEW'):
            return f'Application is {obj.status.lower()}.'

        if (
            user.role != stage.role_required
            and user.role != 'HQ_ADMIN'
            and not user.is_superuser
        ):
            return f'Requires {stage.role_required} role.'

        if stage.is_final and obj.submitted_by_id == user.id:
            return 'You submitted this application; a different user must approve.'

        if stage.order == 1 and obj.created_by_id == user.id:
            return 'You created this application; a different officer must review it.'

        last = obj.transitions.order_by('-created_at').first()
        if last and last.user_id == user.id:
            return (
                f'You performed the last action ({last.action}); '
                f'a different user must act next.'
            )

        return ''


class LoanApplicationCreateSerializer(serializers.ModelSerializer):
    # Derived from request.user in the viewset, never sent by the client
    branch = serializers.PrimaryKeyRelatedField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    # Allow nested creation of guarantors
    guarantors = GuarantorSerializer(many=True, required=False)

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'application_number', 'organization', 'branch', 'client',
            'loan_product', 'loan_officer',
            'requested_amount', 'requested_tenure_months',
            'requested_repayment_frequency', 'purpose', 'purpose_notes',
            'monthly_income', 'monthly_expenses', 'existing_debts', 'net_worth',
            'collateral_summary', 'appraisal_notes', 'guarantors', # guarantor_summary removed
            'status', 'created_at', 'submitted_at',
        ]
        read_only_fields = [
            'id', 'application_number', 'organization', 'branch',
            'status', 'created_at', 'submitted_at',
        ]
        
    def validate_requested_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Requested amount must be positive.')
        return value

    def create(self, validated_data):
        from .services import ApplicationNumberService
        
        # 1. Pop the guarantors data out
        guarantors_data = validated_data.pop('guarantors', [])
        
        user = self.context['request'].user
        validated_data['organization'] = user.organization
        validated_data['created_by'] = user
        validated_data['application_number'] = ApplicationNumberService.generate(
            user.organization,
        )
        
        # 2. Create the main application
        application = super().create(validated_data)
        
        # 3. Create the guarantors linked to the application
        for g_data in guarantors_data:
            Guarantor.objects.create(application=application, **g_data)
            
        return application


class ApplicationActionSerializer(serializers.Serializer):
    comments = serializers.CharField(required=False, allow_blank=True, default='')


class TaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    comments = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'created_by', 'created_at', 'updated_at', 'completed_at',
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_comments(self, obj):
        return [
            {
                'id': c.id,
                'user': c.user.username if c.user else None,
                'comment': c.comment,
                'created_at': c.created_at,
            }
            for c in obj.comments.all()
        ]


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'title', 'description', 'assigned_to', 'branch',
            'related_type', 'related_id', 'priority', 'due_date',
        ]

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['organization'] = user.organization
        validated_data['created_by'] = user
        if not validated_data.get('branch'):
            validated_data['branch'] = getattr(user, 'branch', None)
        return super().create(validated_data)


class TaskActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default='')


class TaskReassignSerializer(serializers.Serializer):
    assigned_to = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, default='')


# ============================================================
# CUSTOMER APP SERIALIZERS (Added Below)
# ============================================================

class CustomerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        # Based on your portal/views.py, your Payment model likely has these fields
        fields = ['id', 'amount', 'received_at', 'payment_method'] 

class CustomerLoanSerializer(serializers.ModelSerializer):
    # This nests the payments inside the loan data for the customer to see
    payments = CustomerPaymentSerializer(many=True, read_only=True)
    
    # NEW: Expose the MFI name
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = Loan
        fields = [
            'id', 'loan_number', 'balance_due', 'is_fully_repaid', 
            'status', 'organization_name', 'payments' 
        ]

