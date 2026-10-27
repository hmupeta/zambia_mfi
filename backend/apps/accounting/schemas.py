from rest_framework import serializers


# ============================================================
# Trial Balance
# ============================================================
class TrialBalanceRowSerializer(serializers.Serializer):
    account__code = serializers.CharField()
    account__name = serializers.CharField()
    account__account_type = serializers.CharField()
    total_debit = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)
    total_credit = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)


class TrialBalanceResponseSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    rows = TrialBalanceRowSerializer(many=True)


# ============================================================
# Income Statement
# ============================================================
class IncomeStatementLineSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    type = serializers.CharField()
    amount = serializers.FloatField()


class IncomeStatementResponseSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    revenue = serializers.FloatField()
    expenses = serializers.FloatField()
    net_income = serializers.FloatField()
    accounts = IncomeStatementLineSerializer(many=True)


# ============================================================
# Balance Sheet
# ============================================================
class BalanceSheetLineSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    amount = serializers.FloatField()
    is_contra = serializers.BooleanField()


class BalanceSheetResponseSerializer(serializers.Serializer):
    as_of_date = serializers.DateField()
    assets = BalanceSheetLineSerializer(many=True)
    liabilities = BalanceSheetLineSerializer(many=True)
    equity = BalanceSheetLineSerializer(many=True)
    total_assets = serializers.FloatField()
    total_liabilities = serializers.FloatField()
    total_equity = serializers.FloatField()
    balanced = serializers.BooleanField()


# ============================================================
# NPL Return (BoZ)
# ============================================================
class NPLRowSerializer(serializers.Serializer):
    branch_code = serializers.CharField()
    loan_number = serializers.CharField()
    client_name = serializers.CharField()
    client_nrc = serializers.CharField()
    product_code = serializers.CharField()
    outstanding_balance = serializers.FloatField()
    days_past_due = serializers.IntegerField()
    classification = serializers.CharField()
    provision_rate = serializers.FloatField()
    provision_amount = serializers.FloatField()
    is_npl = serializers.BooleanField()


class NPLTotalsSerializer(serializers.Serializer):
    total_outstanding = serializers.FloatField()
    total_provision = serializers.FloatField()
    npl_outstanding = serializers.FloatField()
    npl_provision = serializers.FloatField()
    npl_ratio_percent = serializers.FloatField()


class NPLReturnResponseSerializer(serializers.Serializer):
    organization = serializers.CharField()
    as_of_date = serializers.DateField()
    rows = NPLRowSerializer(many=True)
    totals = NPLTotalsSerializer()
    classification_summary = serializers.DictField()


# ============================================================
# Portfolio at Risk
# ============================================================
class PARBucketSerializer(serializers.Serializer):
    overdue_balance = serializers.FloatField()
    ratio_percent = serializers.FloatField()


class PortfolioAtRiskResponseSerializer(serializers.Serializer):
    as_of_date = serializers.DateField()
    total_portfolio = serializers.FloatField()
    par_1 = PARBucketSerializer()
    par_7 = PARBucketSerializer()
    par_30 = PARBucketSerializer()
    par_60 = PARBucketSerializer()
    par_90 = PARBucketSerializer()