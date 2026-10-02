import pytest
from rest_framework.test import APIClient

from agents.models import Agent
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def other_tenant(make_tenant):
    return make_tenant(slug="other-clinic", name="Other Clinic")


@pytest.fixture
def other_client(other_tenant, client_for):
    return client_for(ApiKey.issue(other_tenant, "other").raw_key)


def test_creates_an_agent_for_the_calling_tenant(client, tenant):
    response = client.post("/v1/agents", {"name": "Support", "description": "FAQ"}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Support"
    assert body["published_version"] is None
    assert Agent.objects.get(pk=body["id"]).tenant == tenant


def test_tenant_in_the_payload_is_ignored(client, tenant, other_tenant):
    response = client.post(
        "/v1/agents", {"name": "Support", "tenant": str(other_tenant.pk)}, format="json"
    )

    assert response.status_code == 201
    assert Agent.objects.get(pk=response.json()["id"]).tenant == tenant


@pytest.mark.parametrize("payload", [{}, {"name": "   "}, {"name": "x" * 121}])
def test_invalid_payloads_return_400(client, payload):
    assert client.post("/v1/agents", payload, format="json").status_code == 400


def test_duplicate_name_in_the_same_tenant_returns_400(client, tenant):
    Agent.objects.create(tenant=tenant, name="Support")

    response = client.post("/v1/agents", {"name": "Support"}, format="json")

    assert response.status_code == 400
    assert "name" in response.json()


def test_same_name_is_allowed_in_another_tenant(client, other_tenant):
    Agent.objects.create(tenant=other_tenant, name="Support")

    assert client.post("/v1/agents", {"name": "Support"}, format="json").status_code == 201


def test_lists_only_own_agents(client, other_client, tenant, other_tenant):
    Agent.objects.create(tenant=tenant, name="Mine")
    Agent.objects.create(tenant=other_tenant, name="Theirs")

    assert [a["name"] for a in client.get("/v1/agents").json()] == ["Mine"]
    assert [a["name"] for a in other_client.get("/v1/agents").json()] == ["Theirs"]


def test_retrieves_updates_and_deletes_an_agent(client, tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")

    assert client.get(f"/v1/agents/{agent.pk}").json()["name"] == "Support"
    patched = client.patch(f"/v1/agents/{agent.pk}", {"description": "New"}, format="json")
    assert patched.status_code == 200
    assert patched.json()["description"] == "New"
    replaced = client.put(f"/v1/agents/{agent.pk}", {"name": "Renamed"}, format="json")
    assert replaced.status_code == 200
    assert client.delete(f"/v1/agents/{agent.pk}").status_code == 204
    assert not Agent.objects.filter(pk=agent.pk).exists()


def test_renaming_to_its_own_name_is_allowed(client, tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")

    response = client.put(f"/v1/agents/{agent.pk}", {"name": "Support"}, format="json")

    assert response.status_code == 200


def test_another_tenants_agent_is_invisible(client, other_tenant):
    foreign = Agent.objects.create(tenant=other_tenant, name="Theirs")
    url = f"/v1/agents/{foreign.pk}"

    assert client.get(url).status_code == 404
    assert client.patch(url, {"name": "Hacked"}, format="json").status_code == 404
    assert client.delete(url).status_code == 404
    foreign.refresh_from_db()
    assert foreign.name == "Theirs"


def test_requires_authentication():
    assert APIClient().get("/v1/agents").status_code == 401
    assert APIClient().post("/v1/agents", {"name": "x"}, format="json").status_code == 401
