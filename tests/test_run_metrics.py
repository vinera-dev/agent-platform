from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from agents.models import Agent, Run
from agents.pricing import estimate_cost
from agents.providers import Completion, FakeProvider, ProviderError
from agents.tasks import execute_run

pytestmark = pytest.mark.django_db

USAGE = {"prompt_tokens": 1000, "completion_tokens": 500}


@pytest.fixture
def run(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    version = agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini")
    version.publish()
    return Run.objects.create(tenant=tenant, agent_version=version, input={"message": "hi"})


@pytest.fixture
def clock(monkeypatch):
    start = timezone.now()
    ticks = iter([start, start + timedelta(milliseconds=1250)])
    monkeypatch.setattr("agents.models.timezone.now", lambda: next(ticks))
    return start


def test_cost_uses_the_configured_rates():
    assert estimate_cost("gpt-4o-mini", 1000, 500) == Decimal("0.000450")
    assert estimate_cost("gpt-4o", 1_000_000, 1_000_000) == Decimal("12.500000")


def test_unknown_models_cost_nothing():
    assert estimate_cost("mystery-model", 1000, 1000) == Decimal("0.000000")


def test_rates_can_be_overridden(settings):
    settings.MODEL_PRICING = {"gpt-4o-mini": {"input": 1, "output": 2}}

    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("3.000000")


def test_a_succeeded_run_records_tokens_cost_and_latency(run, clock):
    run.mark_running()
    run.mark_succeeded({"text": "ok", "usage": USAGE})
    run.refresh_from_db()

    assert run.prompt_tokens == 1000
    assert run.completion_tokens == 500
    assert run.estimated_cost_usd == Decimal("0.000450")
    assert run.latency_ms == 1250


def test_a_failed_run_records_latency_but_no_tokens(run, clock):
    run.mark_running()
    run.mark_failed("boom")
    run.refresh_from_db()

    assert run.latency_ms == 1250
    assert (run.prompt_tokens, run.completion_tokens) == (0, 0)
    assert run.estimated_cost_usd == Decimal("0")


def test_failing_before_starting_has_no_latency(run):
    run.mark_failed("boom")

    assert run.latency_ms is None


def test_output_without_usage_records_zeros(run):
    run.mark_running()
    run.mark_succeeded({"text": "ok"})

    assert (run.prompt_tokens, run.completion_tokens, run.estimated_cost_usd) == (0, 0, 0)


def test_the_task_stores_the_summed_usage(run, monkeypatch):
    provider = FakeProvider(script=[Completion("done", usage=USAGE)])
    monkeypatch.setattr("agents.tasks.get_provider", lambda: provider)

    execute_run.apply(args=[str(run.id)], throw=True)

    run.refresh_from_db()
    assert run.prompt_tokens == 1000
    assert run.estimated_cost_usd == Decimal("0.000450")
    assert run.latency_ms is not None and run.latency_ms >= 0


def test_failed_task_runs_have_a_latency(run, monkeypatch):
    provider = FakeProvider(failures=[ProviderError("bad")])
    monkeypatch.setattr("agents.tasks.get_provider", lambda: provider)

    execute_run.apply(args=[str(run.id)], throw=True)

    run.refresh_from_db()
    assert run.status == Run.Status.FAILED
    assert run.latency_ms is not None


def test_the_runs_api_exposes_the_metrics(run, issued_key, client_for):
    run.mark_running()
    run.mark_succeeded({"text": "ok", "usage": USAGE})

    body = client_for(issued_key.raw_key).get(f"/v1/runs/{run.id}").json()

    assert body["prompt_tokens"] == 1000
    assert body["completion_tokens"] == 500
    assert body["estimated_cost_usd"] == "0.000450"
    assert isinstance(body["latency_ms"], int)
