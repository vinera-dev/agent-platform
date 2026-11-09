import pytest

from agents.models import Agent, Run
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def agent(tenant):
    return Agent.objects.create(tenant=tenant, name="Support")


@pytest.fixture
def published(agent):
    version = agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini")
    version.publish()
    return version


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr("agents.views.execute_run.delay", lambda run_id: calls.append(run_id))
    return calls


def runs_url(agent):
    return f"/v1/agents/{agent.pk}/runs"


def test_creating_a_run_returns_202_and_enqueues_the_task(
    client, agent, published, enqueued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(runs_url(agent), {"input": {"message": "hi"}}, format="json")

    body = response.json()
    assert response.status_code == 202
    assert body["status"] == "pending"
    assert body["agent_version"] == published.number
    assert body["input"] == {"message": "hi"}
    assert enqueued == [body["id"]]
    assert Run.objects.get(pk=body["id"]).tenant == agent.tenant


def test_run_is_not_enqueued_before_commit(client, agent, published, enqueued):
    client.post(runs_url(agent), {"input": {"message": "hi"}}, format="json")

    assert Run.objects.count() == 1


def test_agent_without_published_version_returns_409(client, agent, enqueued):
    agent.new_version(system_prompt="Draft.", model="gpt-4o-mini")

    response = client.post(runs_url(agent), {"input": {"message": "hi"}}, format="json")

    assert response.status_code == 409
    assert Run.objects.count() == 0
    assert enqueued == []


@pytest.mark.parametrize("body", [{}, {"input": {}}, {"input": "text"}, {"input": ["a"]}])
def test_invalid_input_returns_400(client, agent, published, enqueued, body):
    response = client.post(runs_url(agent), body, format="json")

    assert response.status_code == 400
    assert Run.objects.count() == 0


def test_oversized_input_returns_400(client, agent, published, enqueued):
    response = client.post(runs_url(agent), {"input": {"message": "x" * 70000}}, format="json")

    assert response.status_code == 400
    assert Run.objects.count() == 0


def test_unknown_agent_returns_404(client, published, enqueued):
    response = client.post(
        "/v1/agents/00000000-0000-0000-0000-000000000000/runs",
        {"input": {"message": "hi"}},
        format="json",
    )

    assert response.status_code == 404


def test_other_tenants_cannot_run_the_agent(agent, published, enqueued, make_tenant, client_for):
    other = make_tenant(slug="other-clinic", name="Other Clinic")
    other_client = client_for(ApiKey.issue(other, "other").raw_key)

    response = other_client.post(runs_url(agent), {"input": {"message": "hi"}}, format="json")

    assert response.status_code == 404
    assert Run.objects.count() == 0


def test_requires_authentication(agent, published):
    from rest_framework.test import APIClient

    response = APIClient().post(runs_url(agent), {"input": {"message": "hi"}}, format="json")

    assert response.status_code in (401, 403)
