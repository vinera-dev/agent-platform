import re

from django.conf import settings
from rest_framework import serializers

from agents.models import Agent, AgentVersion

MAX_PROMPT_LENGTH = 20000
MAX_TOOLS = 20
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

PARAMETER_BOUNDS = {
    "temperature": (0, 2, False),
    "top_p": (0, 1, False),
    "max_tokens": (1, 8192, True),
}


def _check_parameter(name, value):
    low, high, integer = PARAMETER_BOUNDS[name]
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected):
        kind = "an integer" if integer else "a number"
        raise serializers.ValidationError(f"{name} must be {kind}.")
    if not low <= value <= high:
        raise serializers.ValidationError(f"{name} must be between {low} and {high}.")


class AgentSerializer(serializers.ModelSerializer):
    published_version = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = ["id", "name", "description", "published_version", "created_at", "updated_at"]
        read_only_fields = ["id", "published_version", "created_at", "updated_at"]

    def get_published_version(self, agent) -> int | None:
        published = agent.versions.filter(status=AgentVersion.Status.PUBLISHED).first()
        return published.number if published else None

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        tenant = self.context.get("tenant")
        if tenant is not None:
            duplicates = Agent.objects.for_tenant(tenant).filter(name=value)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError("An agent with this name already exists.")
        return value


class AgentVersionSerializer(serializers.ModelSerializer):
    system_prompt = serializers.CharField(max_length=MAX_PROMPT_LENGTH, trim_whitespace=True)
    model = serializers.CharField(max_length=80)
    parameters = serializers.JSONField(required=False, default=dict)
    tools = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
        max_length=MAX_TOOLS,
    )

    class Meta:
        model = AgentVersion
        fields = [
            "id",
            "number",
            "system_prompt",
            "model",
            "parameters",
            "tools",
            "status",
            "created_at",
            "published_at",
        ]
        read_only_fields = ["id", "number", "status", "created_at", "published_at"]

    def validate_model(self, value):
        if value not in settings.ALLOWED_MODELS:
            allowed = ", ".join(settings.ALLOWED_MODELS)
            raise serializers.ValidationError(f"Unsupported model. Allowed: {allowed}.")
        return value

    def validate_parameters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        unknown = sorted(set(value) - set(PARAMETER_BOUNDS))
        if unknown:
            raise serializers.ValidationError(f"Unknown parameters: {', '.join(unknown)}.")
        for name, item in value.items():
            _check_parameter(name, item)
        return value

    def validate_tools(self, value):
        invalid = [name for name in value if not TOOL_NAME_PATTERN.match(name)]
        if invalid:
            raise serializers.ValidationError(f"Invalid tool names: {', '.join(invalid)}.")
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Tool names must be unique.")
        return value
