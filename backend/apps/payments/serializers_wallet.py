# apps/payments/serializers_wallet.py
from rest_framework import serializers

from .models import BranchWallet, WalletReconciliation


class BranchWalletSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    organization_code = serializers.CharField(source='branch.organization.code', read_only=True)
    total_balance = serializers.SerializerMethodField()
    last_recon_status = serializers.SerializerMethodField()

    class Meta:
        model = BranchWallet
        fields = [
            'id', 'branch', 'branch_code', 'branch_name', 'organization_code',
            'cash_balance', 'mobile_money_balance', 'bank_balance', 'total_balance',
            'last_reconciled_at', 'last_recon_status', 'updated_at',
        ]

    def get_total_balance(self, obj):
        return float(
            (obj.cash_balance or 0)
            + (obj.mobile_money_balance or 0)
            + (obj.bank_balance or 0)
        )

    def get_last_recon_status(self, obj):
        last = obj.branch.wallet_reconciliations.order_by('-reconciled_at').first()
        if not last:
            return None
        return {
            'status': last.status,
            'reconciled_at': last.reconciled_at,
            'variance_total': float(last.variance_total or 0),
        }


class WalletReconciliationSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    reconciled_by_name = serializers.CharField(
        source='reconciled_by.get_full_name', read_only=True,
    )
    resolved_by_name = serializers.CharField(
        source='resolved_by.get_full_name', read_only=True,
    )

    class Meta:
        model = WalletReconciliation
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'reconciliation_number',
            'system_cash', 'system_momo', 'system_bank', 'system_total',
            'physical_total', 'variance_cash', 'variance_momo',
            'variance_bank', 'variance_total', 'status',
            'reconciled_by', 'reconciled_at',
            'resolved_by', 'resolved_at',
        ]


class ReconcileRequestSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    physical_cash = serializers.DecimalField(max_digits=14, decimal_places=2)
    physical_momo = serializers.DecimalField(max_digits=14, decimal_places=2)
    physical_bank = serializers.DecimalField(max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class ResolveReconciliationSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=True, allow_blank=False)