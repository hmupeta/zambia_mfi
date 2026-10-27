from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import FieldCollection
from .serializers import FieldCollectionSerializer  # <--- Added import
from apps.core.permissions import IsAuthenticatedStaff, IsHQOrBranchManager
from .services_admin import record_payment

class FieldCollectionViewSet(viewsets.ModelViewSet):
    queryset = FieldCollection.objects.none()
    serializer_class = FieldCollectionSerializer # <--- Added this
    permission_classes = [IsAuthenticatedStaff]
    
    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return FieldCollection.objects.none()
        return FieldCollection.objects.filter(organization=org).select_related('loan', 'loan__client', 'recorded_by').order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            branch=self.request.user.branch,
            recorded_by=self.request.user
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def approve(self, request, pk=None):
        collection = self.get_object()
        if collection.status != 'PENDING':
            return Response({'error': 'Already processed.'}, status=400)

        try:
            record_payment(
                loan=collection.loan,
                amount=collection.amount,
                user=request.user,
                payment_method=collection.payment_method,
                transaction_ref=collection.transaction_ref,
                notes=f"Approved from field sync. Officer: {collection.recorded_by.username}. {collection.notes}"
            )
            
            collection.status = 'APPROVED'
            collection.reviewed_by = request.user
            collection.reviewed_at = timezone.now()
            collection.save()
            
            return Response({'status': 'Payment approved and posted to loan.'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reject(self, request, pk=None):
        collection = self.get_object()
        collection.status = 'REJECTED'
        collection.reviewed_by = request.user
        collection.reviewed_at = timezone.now()
        collection.save()
        return Response({'status': 'Collection rejected.'})