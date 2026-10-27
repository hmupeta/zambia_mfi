# apps/clients/serializers_admin.py
from decimal import Decimal
from datetime import date

from django.db.models import Sum
from rest_framework import serializers

from .models import Client, Guarantor, ClientDocument, ClientPaymentChannel


# ============================================================
# Related models
# ============================================================
class GuarantorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guarantor
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ClientDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ClientDocument
        fields = ['id', 'document_type', 'file', 'file_url', 'uploaded_at']

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url


class ClientPaymentChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientPaymentChannel
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


# ============================================================
# Client â€” list
# ============================================================
class ClientListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source='branch.code', read_only=True, default=None)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    kyc_status_display = serializers.SerializerMethodField()
    active_loans_count = serializers.SerializerMethodField()   # â† computed, not annotation
    outstanding_balance = serializers.SerializerMethodField()  # â† computed, not annotation
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'nrc', 'first_name', 'last_name', 'full_name',
            'gender', 'phone', 'alt_phone', 'email',
            'district', 'province',
            'kyc_status', 'kyc_status_display', 'credit_score',
            'branch', 'branch_code', 'branch_name',
            'active_loans_count', 'outstanding_balance',
            'photo_url', 'is_active', 'created_at',
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip() or obj.nrc

    def get_kyc_status_display(self, obj):
        return (obj.kyc_status or '').replace('_', ' ').title()

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url

    def get_active_loans_count(self, obj):
        # Prefer the annotation if the queryset provided it
        ann = getattr(obj, 'active_loans_count', None)
        if ann is not None and not hasattr(ann, '__iter__'):
            return ann
        return obj.loans.filter(is_fully_repaid=False).count()

    def get_outstanding_balance(self, obj):
        ann = getattr(obj, 'outstanding_balance', None)
        if ann is not None and not hasattr(ann, '__iter__'):
            return float(ann)
        total = obj.loans.filter(is_fully_repaid=False).aggregate(
            s=Sum('balance_due')
        )['s'] or Decimal('0')
        return float(total)


# ============================================================
# Client â€” detail
# ============================================================
class ClientDetailSerializer(ClientListSerializer):
    guarantors = GuarantorSerializer(many=True, read_only=True)
    documents = ClientDocumentSerializer(many=True, read_only=True)
    payment_channels = ClientPaymentChannelSerializer(many=True, read_only=True)
    summary = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta(ClientListSerializer.Meta):
        fields = ClientListSerializer.Meta.fields + [
            'date_of_birth', 'marital_status',
            'occupation', 'employer_name', 'employer_address',
            'home_address', 'village_or_area',
            'national_id_front', 'national_id_back',
            'guarantors', 'documents', 'payment_channels',
            'summary', 'created_by', 'created_by_name',
            'updated_at', 'deleted_at',
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        name = f"{obj.created_by.first_name or ''} {obj.created_by.last_name or ''}".strip()
        return name or obj.created_by.username

    def get_summary(self, obj):
        loans = obj.loans.all()
        active = loans.filter(is_fully_repaid=False)

        total_borrowed = sum(float(l.amount or 0) for l in loans)
        outstanding = sum(float(l.balance_due or 0) for l in active)
        total_paid = float(obj.payments.aggregate(s=Sum('amount'))['s'] or 0)

        # Max days past due across all active loans
        dpd = 0
        today = date.today()
        for loan in active:
            for inst in loan.installments.all():
                if inst.is_paid or (inst.paid_amount or 0) >= (inst.total_due or 0):
                    continue
                if inst.due_date and inst.due_date < today:
                    dpd = max(dpd, (today - inst.due_date).days)

        return {
            'total_borrowed': round(total_borrowed, 2),
            'outstanding': round(outstanding, 2),
            'total_paid': round(total_paid, 2),
            'active_loans': active.count(),
            'total_loans': loans.count(),
            'closed_loans': loans.filter(is_fully_repaid=True).count(),
            'current_dpd': dpd,
        }


# ============================================================
# Client â€” write (create / update)
# ============================================================
class ClientWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            'nrc', 'first_name', 'last_name', 'gender', 'date_of_birth',
            'marital_status', 'phone', 'alt_phone', 'email',
            'occupation', 'employer_name', 'employer_address',
            'home_address', 'village_or_area', 'district', 'province',
            'branch', 'photo', 'national_id_front', 'national_id_back',
            'is_active',
        ]

    def validate_nrc(self, value):
        org = self.context['request'].user.organization
        qs = Client.objects.filter(organization=org, nrc=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A client with this NRC already exists.')
        return value

    def validate_phone(self, value):
        if not value or len(value.strip()) < 9:
            raise serializers.ValidationError('Provide a valid phone number.')
        return value.strip()

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['organization'] = user.organization
        validated_data['created_by'] = user
        validated_data.setdefault('kyc_status', 'PENDING')
        return super().create(validated_data)
