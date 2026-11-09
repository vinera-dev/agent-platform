from urllib.parse import urlsplit

from rest_framework import serializers

from agents.serializers import TOOL_NAME_PATTERN
from tools.executor import url_allowed
from tools.models import Tool
from tools.schema import InvalidToolSchema, validate_input_schema


class ToolSerializer(serializers.ModelSerializer):
    input_schema = serializers.JSONField()
    endpoint_url = serializers.URLField(max_length=500)

    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "description",
            "input_schema",
            "endpoint_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        if not TOOL_NAME_PATTERN.match(value):
            raise serializers.ValidationError(
                "Must start with a lowercase letter and use only lowercase letters, digits "
                "and underscores (up to 64 characters)."
            )
        tenant = self.context.get("tenant")
        if tenant is not None:
            duplicates = Tool.objects.for_tenant(tenant).filter(name=value)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError("A tool with this name already exists.")
        return value

    def validate_input_schema(self, value):
        try:
            return validate_input_schema(value)
        except InvalidToolSchema as error:
            raise serializers.ValidationError(str(error)) from error

    def validate_endpoint_url(self, value):
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise serializers.ValidationError("Must be an http or https URL.")
        if parts.username or parts.password:
            raise serializers.ValidationError("Credentials in the URL are not allowed.")
        if not url_allowed(value):
            raise serializers.ValidationError(f"The domain {parts.hostname} is not allowed.")
        return value


class ToolCreatedSerializer(ToolSerializer):
    signing_secret = serializers.CharField(read_only=True)

    class Meta(ToolSerializer.Meta):
        fields = [*ToolSerializer.Meta.fields, "signing_secret"]
        read_only_fields = [*ToolSerializer.Meta.read_only_fields, "signing_secret"]
