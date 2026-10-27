from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated # <-- Added for Customer API
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import (
    IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager,
)
from apps.core.mixins import OrganizationScopedMixin, AuditLogMixin

from apps.loans.models import Loan # <-- Added for Customer API

from .models import (
    WorkflowTemplate, LoanApplication, ApplicationDocument,
    ApplicationTransition, ApplicationReview, Task,
)
from .serializers import (
    WorkflowTemplateSerializer,
    LoanApplicationSerializer,
    LoanApplicationCreateSerializer,
    ApplicationDocumentSerializer,
    ApplicationTransitionSerializer,
    ApplicationReviewSerializer,
    TaskSerializer,
    TaskCreateSerializer,
    ApplicationActionSerializer,
    TaskActionSerializer,
    TaskReassignSerializer,
    CustomerLoanSerializer, # <-- Added for Customer API
)
from .services import ApplicationService, TaskService
from rest_framework.views import APIView
from apps.clients.models import Client
from apps.loans.models import LoanProduct
from .services import ApplicationNumberService, ApplicationService
from decimal import Decimal


# ============================================================
# Workflow Templates
# ============================================================
class WorkflowTemplateViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = WorkflowTemplate.objects.none()
    serializer_class = WorkflowTemplateSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_default', 'loan_product']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# Loan Applications
# ============================================================
class LoanApplicationViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = LoanApplication.objects.none()
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'LoanApplication'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'branch', 'client', 'loan_product', 'current_stage']
    search_fields = ['application_number', 'client__first_name', 'client__last_name']
    ordering_fields = ['created_at', 'submitted_at', 'requested_amount']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related(
            'client', 'branch', 'loan_product', 'loan_officer',
            'current_stage', 'workflow_template', 'loan',
        ).prefetch_related(
            'documents', 'transitions', 'reviews', 'guarantors'
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def get_serializer_class(self):
        if self.action == 'create':
            return LoanApplicationCreateSerializer
        return LoanApplicationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # These fields are derived from the logged-in staff user, never
        # trusted from the client payload.
        branch = request.user.branch
        if not branch:
            return Response(
                {'branch': ['Your user account has no branch assigned. '
                            'Contact your administrator.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        save_kwargs = {
            'organization': request.user.organization,
            'branch': branch,
            'created_by': request.user,
        }
        # Default the officer to the creator if the client didn't specify one.
        if not serializer.validated_data.get('loan_officer'):
            save_kwargs['loan_officer'] = request.user

        application = serializer.save(**save_kwargs)

        self.log_audit('CREATE', 'LoanApplication', application.id,
                    new_values=LoanApplicationSerializer(application).data,
                    obj=application)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------- Aggregate stats for the list header ----------
    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total':     qs.count(),
            'draft':     qs.filter(status='DRAFT').count(),
            'submitted': qs.filter(status='SUBMITTED').count(),
            'in_review': qs.filter(status='UNDER_REVIEW').count(),
            'approved':  qs.filter(status='APPROVED').count(),
            'rejected':  qs.filter(status='REJECTED').count(),
            'disbursed': qs.filter(status='DISBURSED').count(),
        })

    # ---------- Workflow actions ----------
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        application = self.get_object()
        s = ApplicationActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            ApplicationService.submit(application, request.user, s.validated_data['comments'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )

    @action(detail=True, methods=['post'])
    def advance(self, request, pk=None):
        application = self.get_object()
        s = ApplicationActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            ApplicationService.advance(application, request.user, s.validated_data['comments'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reject(self, request, pk=None):
        application = self.get_object()
        s = ApplicationActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            ApplicationService.reject(application, request.user, s.validated_data['comments'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )

    @action(detail=True, methods=['post'])
    def return_to_applicant(self, request, pk=None):
        application = self.get_object()
        s = ApplicationActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            ApplicationService.return_to_applicant(application, request.user, s.validated_data['comments'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        application = self.get_object()
        s = ApplicationActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            ApplicationService.withdraw(application, request.user, s.validated_data['comments'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )

    # ---------- Disburse (NEW) ----------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def disburse(self, request, pk=None):
        """
        APPROVED -> DISBURSED.
        Posts GL: DR Loans Receivable / CR Cash|Bank|MoMo
        """
        application = self.get_object()

        channel = (request.data.get('channel') or 'BANK').upper()
        reference = (request.data.get('reference') or '').strip()
        when_raw = request.data.get('date')

        try:
            from datetime import date as _date
            disbursement_date = _date.fromisoformat(when_raw) if when_raw else _date.today()
        except ValueError:
            return Response(
                {'error': 'Invalid date format (use YYYY-MM-DD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            application = ApplicationService.disburse(
                application=application,
                user=request.user,
                channel=channel,
                reference=reference,
                disbursement_date=disbursement_date,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Disbursement failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            LoanApplicationSerializer(application, context={'request': request}).data
        )


# ============================================================
# Application Documents
# ============================================================
class ApplicationDocumentViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = ApplicationDocument.objects.none()
    serializer_class = ApplicationDocumentSerializer
    org_field = 'application__organization'
    permission_classes = [IsAuthenticatedStaff]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


# ============================================================
# Transitions (read-only)
# ============================================================
class ApplicationTransitionViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ApplicationTransition.objects.none()
    serializer_class = ApplicationTransitionSerializer
    org_field = 'application__organization'
    permission_classes = [IsAuthenticatedStaff]


# ============================================================
# Reviews
# ============================================================
class ApplicationReviewViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = ApplicationReview.objects.none()
    serializer_class = ApplicationReviewSerializer
    org_field = 'application__organization'
    permission_classes = [IsAuthenticatedStaff]

    def perform_create(self, serializer):
        serializer.save(reviewer=self.request.user)


# ============================================================
# Tasks
# ============================================================
class TaskViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Task.objects.none()
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'assigned_to', 'related_type', 'branch']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('assigned_to', 'created_by', 'branch').prefetch_related('comments')

    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        return TaskSerializer

    @action(detail=False, methods=['get'])
    def mine(self, request):
        qs = self.get_queryset().filter(assigned_to=request.user).order_by('due_date')
        return Response(TaskSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        s = TaskActionSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            TaskService.complete(task, request.user, s.validated_data.get('comment', ''))
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=['post'])
    def reassign(self, request, pk=None):
        task = self.get_object()
        s = TaskReassignSerializer(data=request.data); s.is_valid(raise_exception=True)
        from apps.core.models import User
        try:
            assignee = User.objects.get(pk=s.validated_data['assigned_to'])
        except User.DoesNotExist:
            return Response({'error': 'Assignee not found.'}, status=status.HTTP_400_BAD_REQUEST)
        TaskService.reassign(task, assignee, request.user, s.validated_data.get('comment', ''))
        return Response(TaskSerializer(task).data)


# ============================================================
# CUSTOMER APP VIEWSET (Added Below)
# ============================================================
class CustomerLoanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for the Customer App. 
    Returns only the loans belonging to the logged-in user.
    """
    serializer_class = CustomerLoanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 1. Prevent Swagger from crashing when generating the API docs
        if getattr(self, 'swagger_fake_view', False):
            return Loan.objects.none()

        # 2. Safely extract client_id from the JWT token
        client_id = None
        if hasattr(self.request.auth, 'payload'):
            # SimpleJWT stores the data in a payload object
            client_id = self.request.auth.payload.get('client_id')
        elif isinstance(self.request.auth, dict):
            # Fallback if it's a standard dict
            client_id = self.request.auth.get('client_id')

        # 3. Filter the Loan table and return it
        if client_id:
            return Loan.objects.filter(client_id=client_id).order_by('-created_at')
        
        # 4. Fallback if no client_id is found
        return Loan.objects.none()

class CustomerApplyLoanView(APIView):
    """
    API endpoint for customers to submit a new loan application.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1. Get the Client from the JWT token (Safely handle both dict and AccessToken)
        client_id = None
        if hasattr(request.auth, 'payload'):
            client_id = request.auth.payload.get('client_id')
        elif isinstance(request.auth, dict):
            client_id = request.auth.get('client_id')

        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return Response({'error': 'Client profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not client.branch:
            return Response({'error': 'You are not assigned to a branch. Please contact your branch.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Validate payload
        product_id = request.data.get('loan_product')
        amount_raw = request.data.get('requested_amount')
        tenure_raw = request.data.get('requested_tenure_months')
        frequency = request.data.get('requested_repayment_frequency', 'MONTHLY')
        purpose = request.data.get('purpose', 'BUSINESS_CAPITAL')
        purpose_notes = request.data.get('purpose_notes', '')

        if not product_id or not amount_raw or not tenure_raw:
            return Response({'error': 'Missing required fields: loan_product, requested_amount, requested_tenure_months.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- FIX: Convert Flutter strings to Decimal and Int ---
        try:
            amount = Decimal(str(amount_raw))
            tenure = int(tenure_raw)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount or tenure format.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = LoanProduct.objects.get(id=product_id, organization=client.organization, is_active=True)
        except LoanProduct.DoesNotExist:
            return Response({'error': 'Invalid or inactive loan product.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Get a system user to attribute the application to (since the customer isn't a staff user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        system_user = User.objects.filter(username=f'system@{client.organization.code}').first()
        
        # If system user doesn't exist, create one
        if not system_user:
            system_user = User.objects.create_user(
                username=f'system@{client.organization.code}',
                password='system-unusable-password',
                role='HQ_ADMIN',
                organization=client.organization
            )

        # 4. Create the Application
        try:
            application = LoanApplication.objects.create(
                organization=client.organization,
                branch=client.branch,
                client=client,
                loan_product=product,
                application_number=ApplicationNumberService.generate(client.organization),
                requested_amount=amount,         # <--- Uses Decimal
                requested_tenure_months=tenure,  # <--- Uses Int
                requested_repayment_frequency=frequency,
                purpose=purpose,
                purpose_notes=purpose_notes,
                status='DRAFT',
                created_by=system_user
            )

            # 5. Submit to Workflow (Routes to Loan Officer -> Branch Manager)
            ApplicationService.submit(application, user=system_user)
            application.refresh_from_db()

            return Response({
                'success': True, 
                'message': 'Application submitted successfully. It will be reviewed by a loan officer.',
                'application_number': application.application_number
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Rollback the half-created application if anything fails
            if 'application' in locals() and application.pk:
                application.delete()
                
            return Response({'error': f'Could not submit application: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)