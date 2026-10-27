from rest_framework import serializers
from .models import NotificationChannelConfig, NotificationTemplate, NotificationLog


class NotificationChannelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannelConfig
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'updated_at']


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at', 'is_system']


class NotificationLogSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    template_key = serializers.CharField(source='template.key', read_only=True)
    sent_by_name = serializers.CharField(source='sent_by.get_full_name', read_only=True)

    class Meta:
        model = NotificationLog
        fields = '__all__'

    def get_client_name(self, obj):
        if not obj.client:
            return ''
        return (obj.client.first_name + ' ' + obj.client.last_name).strip()


class SendOneOffSerializer(serializers.Serializer):
    client = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=['SMS', 'WHATSAPP', 'EMAIL'])
    body = serializers.CharField(required=False, allow_blank=True)
    subject = serializers.CharField(required=False, allow_blank=True, default='')
    template_key = serializers.CharField(required=False, allow_blank=True)
    context = serializers.DictField(required=False, default=dict)


class SendBulkSerializer(serializers.Serializer):
    template_key = serializers.CharField()
    channel = serializers.ChoiceField(choices=['SMS', 'WHATSAPP', 'EMAIL', 'BOTH', 'ALL'])
    client_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    statuses = serializers.ListField(child=serializers.CharField(), required=False)
