import json

from rest_framework import serializers

from agents.models import Agent
from evaluation.models import EvalCase, EvalDataset

MAX_CONTAINS = 20
MAX_CASE_INPUT_BYTES = 16 * 1024


class EvalDatasetSerializer(serializers.ModelSerializer):
    agent = serializers.UUIDField(source="agent_id")
    case_count = serializers.IntegerField(source="cases.count", read_only=True)

    class Meta:
        model = EvalDataset
        fields = ["id", "name", "description", "agent", "case_count", "created_at"]
        read_only_fields = ["id", "case_count", "created_at"]

    def validate_agent(self, value):
        tenant = self.context["tenant"]
        if not Agent.objects.for_tenant(tenant).filter(pk=value).exists():
            raise serializers.ValidationError("Unknown agent.")
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        duplicates = EvalDataset.objects.for_tenant(self.context["tenant"]).filter(name=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A dataset with this name already exists.")
        return value


class EvalCaseSerializer(serializers.ModelSerializer):
    input = serializers.JSONField()
    expected_contains = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        default=list,
        max_length=MAX_CONTAINS,
    )

    class Meta:
        model = EvalCase
        fields = ["id", "name", "input", "expected_output", "expected_contains", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_input(self, value):
        if not isinstance(value, dict) or not value:
            raise serializers.ValidationError("Must be a non-empty object.")
        if len(json.dumps(value)) > MAX_CASE_INPUT_BYTES:
            raise serializers.ValidationError(f"Must not exceed {MAX_CASE_INPUT_BYTES} bytes.")
        return value

    def validate_expected_contains(self, value):
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise serializers.ValidationError("Entries must not be blank.")
        return cleaned

    def validate(self, attrs):
        merged = {
            "expected_output": getattr(self.instance, "expected_output", ""),
            "expected_contains": getattr(self.instance, "expected_contains", []),
            **attrs,
        }
        if not merged["expected_output"].strip() and not merged["expected_contains"]:
            raise serializers.ValidationError(
                "Provide expected_output, expected_contains, or both."
            )
        return attrs
