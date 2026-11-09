import json

import httpx
import pytest

from agents.models import Agent, Run
from agents.providers import Completion, FakeProvider, ToolCall
from agents.tasks import execute_run
from tools.executor import DomainNotAllowed, execute_tool
from tools.models import Tool

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "properties": {"date": {"type": "string"}},
    "required": ["date"],
}
USAGE = {"prompt_tokens": 10, "completion_tokens": 5}


def ask(call_id="c1", name="lookup_slots", arguments=None):
    arguments = {"date": "2026-01-05"} if arguments is None else arguments
    return Completion(text="", usage=USAGE, tool_calls=(ToolCall(call_id, name, arguments),))


def answer(text="Slots are 09:00 and 10:30."):
    return Completion(text=text, usage=USAGE)


@pytest.fixture
def make_tool(tenant):
    def factory(owner=None, **extra):
        fields = {
            "tenant": owner or tenant,
            "name": "lookup_slots",
            "description": "Find free slots.",
            "input_schema": SCHEMA,
            "endpoint_url": "https://scheduler.example.com/slots",
        }
        return Tool.objects.create(**{**fields, **extra})

    return factory


@pytest.fixture
def make_run(tenant):
    def factory(tools=("lookup_slots",)):
        agent = Agent.objects.create(tenant=tenant, name="Scheduler")
        version = agent.new_version(
            system_prompt="Book appointments.", model="gpt-4o-mini", tools=list(tools)
        )
        version.publish()
        return Run.objects.create(
            tenant=tenant, agent_version=version, input={"message": "Any slots on Monday?"}
        )

    return factory


@pytest.fixture
def provider(monkeypatch):
    instance = FakeProvider()
    monkeypatch.setattr("agents.tasks.get_provider", lambda: instance)
    return instance


@pytest.fixture
def calls(monkeypatch):
    seen = []
    mock = httpx.MockTransport(
        lambda request: (
            seen.append(json.loads(request.content))
            or httpx.Response(200, json={"slots": ["09:00", "10:30"]})
        )
    )
    monkeypatch.setattr(
        "agents.execution.execute_tool",
        lambda tool, arguments: execute_tool(tool, arguments, transport=mock),
    )
    return seen


def finish(run):
    execute_run.apply(args=[str(run.id)], throw=True)
    run.refresh_from_db()
    return run


def test_model_requests_a_tool_and_receives_its_result(make_tool, make_run, provider, calls):
    make_tool()
    provider.script = [ask(), answer()]

    run = finish(make_run())

    assert run.status == Run.Status.SUCCEEDED
    assert run.output["text"] == "Slots are 09:00 and 10:30."
    assert calls == [{"arguments": {"date": "2026-01-05"}}]
    assert run.output["tool_calls"] == [
        {
            "name": "lookup_slots",
            "arguments": {"date": "2026-01-05"},
            "ok": True,
            "result": {"slots": ["09:00", "10:30"]},
        }
    ]
    first, second = provider.calls
    assert first["history"] == []
    assert first["tools"] == [
        {"name": "lookup_slots", "description": "Find free slots.", "parameters": SCHEMA}
    ]
    assert [message["role"] for message in second["history"]] == ["assistant", "tool"]
    assert second["history"][0]["tool_calls"][0]["function"] == {
        "name": "lookup_slots",
        "arguments": '{"date": "2026-01-05"}',
    }
    assert second["history"][1]["tool_call_id"] == "c1"
    assert json.loads(second["history"][1]["content"]) == {"result": {"slots": ["09:00", "10:30"]}}


def test_usage_is_summed_across_the_loop(make_tool, make_run, provider, calls):
    make_tool()
    provider.script = [ask(), answer()]

    run = finish(make_run())

    assert run.output["usage"] == {"prompt_tokens": 20, "completion_tokens": 10}


def test_several_tool_calls_in_one_step_are_all_executed(make_tool, make_run, provider, calls):
    make_tool()
    two = Completion(
        text="",
        usage=USAGE,
        tool_calls=(
            ToolCall("a", "lookup_slots", {"date": "2026-01-05"}),
            ToolCall("b", "lookup_slots", {"date": "2026-01-06"}),
        ),
    )
    provider.script = [two, answer()]

    run = finish(make_run())

    assert [call["arguments"]["date"] for call in run.output["tool_calls"]] == [
        "2026-01-05",
        "2026-01-06",
    ]
    assert [message["tool_call_id"] for message in provider.calls[1]["history"][1:]] == ["a", "b"]


def test_loop_stops_at_the_step_limit(make_tool, make_run, provider, calls, settings):
    settings.MAX_TOOL_STEPS = 2
    make_tool()
    provider.script = [ask(f"c{n}") for n in range(10)]

    run = finish(make_run())

    assert run.status == Run.Status.FAILED
    assert "after 2 steps" in run.error
    assert len(provider.calls) == 3
    assert len(calls) == 2


def test_zero_steps_forbid_any_tool_call(make_tool, make_run, provider, calls, settings):
    settings.MAX_TOOL_STEPS = 0
    make_tool()
    provider.script = [ask()]

    run = finish(make_run())

    assert run.status == Run.Status.FAILED
    assert calls == []


def test_tool_errors_are_reported_to_the_model_without_failing_the_run(
    make_tool, make_run, provider, monkeypatch
):
    make_tool()

    def blocked(tool, arguments):
        raise DomainNotAllowed("The domain scheduler.example.com is not in the allow-list.")

    monkeypatch.setattr("agents.execution.execute_tool", blocked)
    provider.script = [ask(), answer("I could not check the schedule.")]

    run = finish(make_run())

    assert run.status == Run.Status.SUCCEEDED
    assert run.output["tool_calls"][0]["ok"] is False
    assert "allow-list" in run.output["tool_calls"][0]["error"]
    assert "allow-list" in json.loads(provider.calls[1]["history"][1]["content"])["error"]


def test_invalid_arguments_from_the_model_are_reported_back(make_tool, make_run, provider, calls):
    make_tool()
    provider.script = [ask(arguments={"day": "monday"}), answer("Sorry.")]

    run = finish(make_run())

    assert run.status == Run.Status.SUCCEEDED
    assert run.output["tool_calls"][0]["ok"] is False
    assert "Invalid arguments" in run.output["tool_calls"][0]["error"]
    assert calls == []


def test_unknown_tool_requests_are_rejected(make_tool, make_run, provider, calls):
    make_tool()
    provider.script = [ask(name="drop_database"), answer("Sorry.")]

    run = finish(make_run())

    assert run.output["tool_calls"][0] == {
        "name": "drop_database",
        "arguments": {"date": "2026-01-05"},
        "ok": False,
        "error": "Unknown tool: drop_database.",
    }
    assert calls == []


def test_only_the_versions_own_active_tools_are_offered(make_tool, make_run, provider, make_tenant):
    make_tool(name="lookup_slots")
    make_tool(name="book_slot")
    make_tool(name="disabled_tool", is_active=False)
    make_tool(owner=make_tenant(slug="other", name="Other"), name="foreign_tool")

    finish(make_run(tools=("lookup_slots", "disabled_tool", "foreign_tool")))

    assert [spec["name"] for spec in provider.calls[0]["tools"]] == ["lookup_slots"]


def test_another_tenants_tool_with_the_same_name_is_never_used(
    make_tool, make_run, provider, calls, make_tenant
):
    make_tool(
        owner=make_tenant(slug="other", name="Other"), endpoint_url="https://other.example.com/x"
    )
    provider.script = [ask(), answer("Sorry.")]

    run = finish(make_run())

    assert run.output["tool_calls"][0]["error"] == "Unknown tool: lookup_slots."
    assert calls == []


def test_agent_without_tools_offers_none(make_run, provider):
    finish(make_run(tools=()))

    assert provider.calls[0]["tools"] == []


def test_version_api_rejects_unknown_tool_names(tenant, issued_key, client_for, make_tool):
    make_tool()
    agent = Agent.objects.create(tenant=tenant, name="Scheduler")
    client = client_for(issued_key.raw_key)
    body = {"system_prompt": "Hi.", "model": "gpt-4o-mini"}

    bad = client.post(
        f"/v1/agents/{agent.pk}/versions", {**body, "tools": ["missing_tool"]}, format="json"
    )
    good = client.post(
        f"/v1/agents/{agent.pk}/versions", {**body, "tools": ["lookup_slots"]}, format="json"
    )

    assert bad.status_code == 400
    assert "missing_tool" in str(bad.json()["tools"])
    assert good.status_code == 201
