from rest_framework import serializers
from .models import Client, ClientPaymentChannel, Guarantor, ClientDocument

class ClientPaymentChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientPaymentChannel
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class GuarantorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guarantor
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class ClientDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDocument
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_at']

class ClientSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    payment_channels = ClientPaymentChannelSerializer(many=True, read_only=True)
    guarantors = GuarantorSerializer(many=True, read_only=True)
    
    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'branch_code', 'branch_name', 'created_by_name']