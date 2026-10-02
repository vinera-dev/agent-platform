from rest_framework import serializers

from tenants.models import ApiKey


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ["id", "name", "prefix", "created_at", "last_used_at", "revoked_at"]
        read_only_fields = fields


class TenantSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.SlugField()
    name = serializers.CharField()


class WhoAmISerializer(serializers.Serializer):
    tenant = TenantSummarySerializer()
