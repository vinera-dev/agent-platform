import pytest

from agents.models import Agent, Run
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db

BODY = {"input": {"message": "hi"}}


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def agent(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini").publish()
    return agent


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr("agents.views.execute_run.delay", lambda run_id: calls.append(run_id))
    return calls


def post(client, agent, key=None, body=BODY):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    return client.post(f"/v1/agents/{agent.pk}/runs", body, format="json", **headers)


def test_repeating_a_call_returns_the_original_run(
    client, agent, enqueued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        first = post(client, agent, "key-1")
        second = post(client, agent, "key-1")

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert Run.objects.count() == 1
    assert enqueued == [first.json()["id"]]
    assert "Idempotent-Replayed" not in first
    assert second["Idempotent-Replayed"] == "true"


def test_calls_without_a_key_are_never_deduplicated(client, agent, enqueued):
    first = post(client, agent)
    second = post(client, agent)

    assert first.json()["id"] != second.json()["id"]
    assert Run.objects.count() == 2


def test_different_keys_create_different_runs(client, agent, enqueued):
    first = post(client, agent, "key-1")
    second = post(client, agent, "key-2")

    assert first.json()["id"] != second.json()["id"]


def test_reusing_a_key_with_another_body_is_rejected(client, agent, enqueued):
    post(client, agent, "key-1")

    response = post(client, agent, "key-1", {"input": {"message": "different"}})

    assert response.status_code == 422
    assert Run.objects.count() == 1


def test_reusing_a_key_for_another_agent_is_rejected(client, tenant, agent, enqueued):
    other = Agent.objects.create(tenant=tenant, name="Sales")
    other.new_version(system_prompt="x", model="gpt-4o-mini").publish()
    post(client, agent, "key-1")

    assert post(client, other, "key-1").status_code == 422


def test_keys_are_scoped_to_the_tenant(client, agent, enqueued, make_tenant, client_for):
    other_tenant = make_tenant(slug="other-clinic", name="Other")
    other_agent = Agent.objects.create(tenant=other_tenant, name="Support")
    other_agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini").publish()
    other_client = client_for(ApiKey.issue(other_tenant, "other").raw_key)

    mine = post(client, agent, "shared-key")
    theirs = post(other_client, other_agent, "shared-key")

    assert mine.status_code == theirs.status_code == 202
    assert mine.json()["id"] != theirs.json()["id"]
    assert Run.objects.count() == 2


def test_replay_returns_the_current_state_of_the_run(client, agent, enqueued):
    first = post(client, agent, "key-1")
    run = Run.objects.get(pk=first.json()["id"])
    run.mark_running()
    run.mark_succeeded({"text": "done"})

    replay = post(client, agent, "key-1")

    assert replay.json()["status"] == "succeeded"
    assert replay.json()["output"] == {"text": "done"}


def test_replay_works_even_if_the_agent_was_unpublished_since(client, agent, enqueued):
    first = post(client, agent, "key-1")
    agent.versions.filter(status="published").update(status="archived")

    replay = post(client, agent, "key-1")

    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert post(client, agent, "key-2").status_code == 409


@pytest.mark.parametrize("key", ["", "has space", "x" * 129, "tab\there"])
def test_invalid_keys_return_400(client, agent, enqueued, key):
    response = post(client, agent, key)

    assert response.status_code == 400
    assert Run.objects.count() == 0


def test_database_enforces_one_run_per_key(tenant, agent):
    from django.db import IntegrityError, transaction

    version = agent.versions.first()
    Run.objects.create(tenant=tenant, agent_version=version, idempotency_key="k")

    with pytest.raises(IntegrityError), transaction.atomic():
        Run.objects.create(tenant=tenant, agent_version=version, idempotency_key="k")
    Run.objects.create(tenant=tenant, agent_version=version)
    Run.objects.create(tenant=tenant, agent_version=version)
