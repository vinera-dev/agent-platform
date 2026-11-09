import io
import json
import logging
import sys

import pytest

from agents.models import Agent, Run
from agents.providers import FakeProvider, ProviderError
from agents.tasks import execute_run
from config.logs import JsonFormatter, bind_log_context, current_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def json_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    def read():
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    yield read
    root.removeHandler(handler)
    root.setLevel(previous_level)


@pytest.fixture
def run(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    version = agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini")
    version.publish()
    return Run.objects.create(tenant=tenant, agent_version=version, input={"message": "hi"})


@pytest.fixture
def provider(monkeypatch):
    instance = FakeProvider()
    monkeypatch.setattr("agents.tasks.get_provider", lambda: instance)
    return instance


def test_run_logs_carry_tenant_and_run_ids(run, provider, json_lines):
    execute_run.apply(args=[str(run.id)], throw=True)

    lines = [line for line in json_lines() if line["logger"].startswith("agents")]
    assert [line["message"] for line in lines] == ["run started", "run finished"]
    for line in lines:
        assert line["tenant_id"] == str(run.tenant_id)
        assert line["run_id"] == str(run.id)
    finished = lines[-1]
    assert finished["status"] == "succeeded"
    assert finished["prompt_tokens"] == 1
    assert finished["level"] == "INFO"


def test_failed_runs_log_the_error_with_the_same_ids(run, provider, json_lines):
    provider.failures = [ProviderError("bad request")]

    execute_run.apply(args=[str(run.id)], throw=True)

    finished = [line for line in json_lines() if line["message"] == "run finished"][0]
    assert finished["status"] == "failed"
    assert finished["error"] == "bad request"
    assert finished["run_id"] == str(run.id)


def test_creating_a_run_through_the_api_logs_the_ids(
    tenant, issued_key, client_for, json_lines, monkeypatch
):
    monkeypatch.setattr("agents.views.execute_run.delay", lambda run_id: None)
    agent = Agent.objects.create(tenant=tenant, name="Support")
    agent.new_version(system_prompt="Hi.", model="gpt-4o-mini").publish()

    response = client_for(issued_key.raw_key).post(
        f"/v1/agents/{agent.pk}/runs", {"input": {"message": "hi"}}, format="json"
    )

    created = [line for line in json_lines() if line["message"] == "run created"][0]
    assert created["tenant_id"] == str(tenant.id)
    assert created["run_id"] == response.json()["id"]


def test_context_is_removed_after_the_block(json_lines):
    logger = logging.getLogger("outside")

    with bind_log_context(tenant_id="t-1", run_id="r-1"):
        logger.info("inside")
    logger.info("after")

    inside, after = json_lines()
    assert inside["tenant_id"] == "t-1"
    assert "tenant_id" not in after
    assert current_context() == {}


def test_nested_contexts_merge_and_restore():
    with bind_log_context(tenant_id="t-1"):
        with bind_log_context(run_id="r-1"):
            assert current_context() == {"tenant_id": "t-1", "run_id": "r-1"}
        assert current_context() == {"tenant_id": "t-1"}


def test_formatter_emits_one_json_object_with_extras_and_exceptions():
    record = logging.LogRecord("demo", logging.ERROR, __file__, 1, "failed %s", ("now",), None)
    record.extra_field = 7
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "failed now"
    assert payload["level"] == "ERROR"
    assert payload["extra_field"] == 7
    assert "ValueError: boom" in payload["exception"]
    assert "timestamp" in payload
