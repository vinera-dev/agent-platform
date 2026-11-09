import pytest
from celery.exceptions import SoftTimeLimitExceeded

from agents.models import Agent, Run
from agents.providers import FakeProvider, ProviderError, TransientProviderError
from agents.tasks import RETRIES_EXHAUSTED_ERROR, TIMEOUT_ERROR, execute_run, retry_delay

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fast_retries(settings):
    settings.RUN_RETRY_BACKOFF_SECONDS = 0
    settings.RUN_MAX_RETRIES = 3
    settings.RUN_TIMEOUT_SECONDS = 12.5


@pytest.fixture
def run(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    version = agent.new_version(
        system_prompt="Be helpful.", model="gpt-4o-mini", parameters={"temperature": 0.1}
    )
    version.publish()
    return Run.objects.create(tenant=tenant, agent_version=version, input={"message": "hi"})


@pytest.fixture
def provider(monkeypatch):
    instance = FakeProvider(reply="answer")
    monkeypatch.setattr("agents.tasks.get_provider", lambda: instance)
    return instance


def run_task(run):
    result = execute_run.apply(args=[str(run.id)], throw=False)
    assert result.successful(), result.result
    run.refresh_from_db()
    return run


def test_successful_run_stores_output_and_times(run, provider, eager):
    run = run_task(run)

    assert run.status == Run.Status.SUCCEEDED
    assert run.output == {
        "text": "answer: hi",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "sources": [],
    }
    assert run.started_at is not None and run.finished_at is not None


def test_provider_receives_the_version_settings(run, provider, eager):
    run_task(run)

    assert provider.calls == [
        {
            "model": "gpt-4o-mini",
            "system_prompt": "Be helpful.",
            "user_input": {"message": "hi"},
            "parameters": {"temperature": 0.1},
            "timeout": 12.5,
        }
    ]


def test_permanent_failure_marks_the_run_failed_without_retrying(run, provider, eager):
    provider.failures = [ProviderError("bad request")]

    run = run_task(run)

    assert run.status == Run.Status.FAILED
    assert run.error == "bad request"
    assert len(provider.calls) == 1


def test_transient_failure_is_retried_until_it_succeeds(run, provider, eager):
    provider.failures = [TransientProviderError("rate limited"), TransientProviderError("again")]

    run = run_task(run)

    assert run.status == Run.Status.SUCCEEDED
    assert len(provider.calls) == 3


def test_run_fails_after_the_retry_limit(run, provider, eager):
    provider.failures = [TransientProviderError("down")] * 10

    run = run_task(run)

    assert run.status == Run.Status.FAILED
    assert len(provider.calls) == 4
    assert run.error == RETRIES_EXHAUSTED_ERROR.format(attempts=4, detail="down")
    assert run.finished_at is not None


def test_time_limit_marks_the_run_failed(run, provider, eager):
    provider.failures = [SoftTimeLimitExceeded()]

    run = run_task(run)

    assert run.status == Run.Status.FAILED
    assert run.error == TIMEOUT_ERROR


def test_finished_runs_are_not_executed_again(run, provider, eager):
    run_task(run)
    run_task(run)

    assert len(provider.calls) == 1


def test_unknown_run_is_ignored(provider, eager):
    result = execute_run.apply(args=["00000000-0000-0000-0000-000000000000"], throw=True)

    assert result.successful()
    assert provider.calls == []


def test_retry_delay_grows_exponentially(settings):
    settings.RUN_RETRY_BACKOFF_SECONDS = 2

    assert [retry_delay(n) for n in range(4)] == [2, 4, 8, 16]


def test_creating_a_run_through_the_api_executes_it(
    tenant, issued_key, client_for, provider, eager, django_capture_on_commit_callbacks
):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini").publish()

    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(issued_key.raw_key).post(
            f"/v1/agents/{agent.pk}/runs", {"input": {"message": "hello"}}, format="json"
        )

    run = Run.objects.get(pk=response.json()["id"])
    assert response.status_code == 202
    assert run.status == Run.Status.SUCCEEDED
    assert run.output["text"] == "answer: hello"
