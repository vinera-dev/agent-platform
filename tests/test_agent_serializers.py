import pytest

from agents.models import Agent
from agents.serializers import (
    MAX_PROMPT_LENGTH,
    MAX_TOOLS,
    AgentSerializer,
    AgentVersionSerializer,
)

pytestmark = pytest.mark.django_db

VALID = {"system_prompt": "Be helpful.", "model": "gpt-4o-mini"}


def version(**overrides):
    return AgentVersionSerializer(data={**VALID, **overrides})


def test_valid_version_passes_with_defaults():
    serializer = version()

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["parameters"] == {}
    assert serializer.validated_data["tools"] == []


def test_valid_version_with_parameters_and_tools():
    serializer = version(
        parameters={"temperature": 0.5, "max_tokens": 512, "top_p": 1},
        tools=["lookup_slots", "book_slot"],
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("system_prompt", ""),
        ("system_prompt", "   "),
        ("system_prompt", "x" * (MAX_PROMPT_LENGTH + 1)),
        ("model", "not-a-model"),
        ("model", ""),
        ("parameters", ["temperature"]),
        ("parameters", {"temperature": 3}),
        ("parameters", {"temperature": -0.1}),
        ("parameters", {"temperature": "hot"}),
        ("parameters", {"temperature": True}),
        ("parameters", {"top_p": 1.5}),
        ("parameters", {"max_tokens": 0}),
        ("parameters", {"max_tokens": 9000}),
        ("parameters", {"max_tokens": 10.5}),
        ("parameters", {"stop": ["x"]}),
        ("tools", ["Bad Name"]),
        ("tools", ["1starts_with_digit"]),
        ("tools", ["a", "a"]),
        ("tools", [f"tool_{i}" for i in range(MAX_TOOLS + 1)]),
        ("tools", "lookup_slots"),
    ],
)
def test_invalid_version_fields_are_reported(field, value):
    serializer = version(**{field: value})

    assert not serializer.is_valid()
    assert field in serializer.errors


def test_missing_required_fields_are_reported():
    serializer = AgentVersionSerializer(data={})

    assert not serializer.is_valid()
    assert {"system_prompt", "model"} <= set(serializer.errors)


def test_server_controlled_fields_are_ignored_on_input():
    serializer = version(number=99, status="published")

    assert serializer.is_valid()
    assert "number" not in serializer.validated_data
    assert "status" not in serializer.validated_data


def test_allowed_models_follow_the_setting(settings):
    settings.ALLOWED_MODELS = ["custom-model"]

    assert version(model="custom-model").is_valid()
    assert not version(model="gpt-4o-mini").is_valid()


def test_agent_name_is_trimmed_and_required():
    assert AgentSerializer(data={"name": "  Support  "}).is_valid()
    assert not AgentSerializer(data={"name": "   "}).is_valid()
    assert not AgentSerializer(data={}).is_valid()


def test_agent_name_must_be_unique_within_the_tenant(tenant, make_tenant):
    existing = Agent.objects.create(tenant=tenant, name="Support")
    context = {"tenant": tenant}

    assert not AgentSerializer(data={"name": "Support"}, context=context).is_valid()
    assert AgentSerializer(existing, data={"name": "Support"}, context=context).is_valid()
    other = make_tenant(slug="other-clinic", name="Other")
    assert AgentSerializer(data={"name": "Support"}, context={"tenant": other}).is_valid()
