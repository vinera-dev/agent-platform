import json

import httpx
import pytest

from agents.execution import TraceEvent
from agents.models import Agent, Run
from agents.providers import Completion, FakeProvider, ProviderError, ToolCall
from agents.tasks import execute_run
from agents.tracing import LangfuseTracer, NullTracer, get_tracer
from tools.models import Tool

pytestmark = pytest.mark.django_db


class RecordingTracer:
    def __init__(self):
        self.traces = []

    def trace_run(self, run, events):
        self.traces.append((run.id, run.status, list(events)))


@pytest.fixture
def provider(monkeypatch):
    instance = FakeProvider(reply="answer")
    monkeypatch.setattr("agents.tasks.get_provider", lambda: instance)
    return instance


@pytest.fixture
def tracer(monkeypatch):
    instance = RecordingTracer()
    monkeypatch.setattr("agents.tracing.get_tracer", lambda: instance)
    return instance


@pytest.fixture
def make_run(tenant):
    def factory(tools=()):
        agent = Agent.objects.create(tenant=tenant, name="Support")
        version = agent.new_version(
            system_prompt="Be helpful.", model="gpt-4o-mini", tools=list(tools)
        )
        version.publish()
        return Run.objects.create(tenant=tenant, agent_version=version, input={"message": "hi"})

    return factory


def test_each_run_produces_exactly_one_trace(make_run, provider, tracer):
    run = make_run()

    execute_run.apply(args=[str(run.id)], throw=True)

    assert len(tracer.traces) == 1
    run_id, status, events = tracer.traces[0]
    assert run_id == run.id
    assert status == "succeeded"
    assert [event.kind for event in events] == ["generation"]
    assert events[0].model == "gpt-4o-mini"
    assert events[0].usage == {"prompt_tokens": 1, "completion_tokens": 1}
    assert events[0].ended_at >= events[0].started_at


def test_tool_calls_are_traced_as_spans(make_run, provider, tracer, tenant, monkeypatch):
    Tool.objects.create(
        tenant=tenant,
        name="lookup_slots",
        description="d",
        input_schema={"type": "object"},
        endpoint_url="https://scheduler.example.com/slots",
    )
    monkeypatch.setattr("agents.execution.execute_tool", lambda tool, arguments: {"slots": []})
    provider.script = [
        Completion("", tool_calls=(ToolCall("c1", "lookup_slots", {}),)),
        Completion("done"),
    ]
    run = make_run(tools=("lookup_slots",))

    execute_run.apply(args=[str(run.id)], throw=True)

    events = tracer.traces[0][2]
    assert [event.kind for event in events] == ["generation", "tool", "generation"]
    assert events[1].name == "lookup_slots"
    assert events[1].output == {"slots": []}


def test_failed_runs_are_traced_with_the_error(make_run, provider, tracer):
    provider.failures = [ProviderError("bad request")]
    run = make_run()

    execute_run.apply(args=[str(run.id)], throw=True)

    _, status, events = tracer.traces[0]
    assert status == "failed"
    assert events[0].error == "bad request"


def test_a_tracing_failure_never_fails_the_run(make_run, provider, monkeypatch):
    class Broken:
        def trace_run(self, run, events):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr("agents.tracing.get_tracer", Broken)
    run = make_run()

    execute_run.apply(args=[str(run.id)], throw=True)

    run.refresh_from_db()
    assert run.status == Run.Status.SUCCEEDED


def test_tracing_is_off_without_langfuse_settings(settings):
    settings.LANGFUSE_HOST = ""
    settings.LANGFUSE_PUBLIC_KEY = "pk"
    settings.LANGFUSE_SECRET_KEY = "sk"

    assert isinstance(get_tracer(), NullTracer)


def test_tracing_is_on_with_all_langfuse_settings(settings):
    settings.LANGFUSE_HOST = "http://127.0.0.1:24300"
    settings.LANGFUSE_PUBLIC_KEY = "pk"
    settings.LANGFUSE_SECRET_KEY = "sk"

    assert isinstance(get_tracer(), LangfuseTracer)


def test_langfuse_tracer_posts_a_trace_and_its_observations(make_run, provider):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(207, json={"successes": [], "errors": []})

    run = make_run()
    execute_run.apply(args=[str(run.id)], throw=True)
    run.refresh_from_db()
    run = Run.objects.select_related("agent_version").get(pk=run.pk)
    tracer = LangfuseTracer(
        "http://langfuse.test/", "pk-test", "sk-test", transport=httpx.MockTransport(handler)
    )

    event = TraceEvent(
        kind="generation",
        name="llm-call",
        started_at=run.started_at,
        ended_at=run.finished_at,
        model="gpt-4o-mini",
        usage={"prompt_tokens": 3, "completion_tokens": 2},
    )
    span = TraceEvent(
        kind="tool", name="lookup", started_at=run.started_at, ended_at=run.finished_at, error="x"
    )
    tracer.trace_run(run, [event, span])

    request = seen[0]
    batch = json.loads(request.content)["batch"]
    assert str(request.url) == "http://langfuse.test/api/public/ingestion"
    assert request.headers["authorization"].startswith("Basic ")
    assert [item["type"] for item in batch] == ["trace-create", "generation-create", "span-create"]
    trace = batch[0]["body"]
    assert trace["id"] == str(run.id)
    assert trace["userId"] == str(run.tenant_id)
    assert trace["metadata"]["run_id"] == str(run.id)
    generation = batch[1]["body"]
    assert generation["traceId"] == str(run.id)
    assert generation["usage"] == {"input": 3, "output": 2, "unit": "TOKENS"}
    assert batch[2]["body"]["level"] == "ERROR"


def test_langfuse_tracer_raises_when_the_server_rejects_events(make_run, provider):
    run = make_run()
    execute_run.apply(args=[str(run.id)], throw=True)
    run = Run.objects.select_related("agent_version").get(pk=run.pk)
    rejecting = httpx.MockTransport(
        lambda request: httpx.Response(207, json={"successes": [], "errors": [{"id": "1"}]})
    )
    failing = httpx.MockTransport(lambda request: httpx.Response(401))

    with pytest.raises(RuntimeError):
        LangfuseTracer("http://x", "pk", "sk", transport=rejecting).trace_run(run, [])
    with pytest.raises(httpx.HTTPStatusError):
        LangfuseTracer("http://x", "pk", "sk", transport=failing).trace_run(run, [])
