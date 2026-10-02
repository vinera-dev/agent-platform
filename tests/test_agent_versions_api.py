import pytest
from rest_framework.test import APIClient

from agents.models import Agent, AgentVersion
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db

BODY = {
    "system_prompt": "Be helpful.",
    "model": "gpt-4o-mini",
    "parameters": {"temperature": 0.2},
    "tools": ["lookup_slots"],
}


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def agent(tenant):
    return Agent.objects.create(tenant=tenant, name="Support")


@pytest.fixture
def other_client(make_tenant, client_for):
    other = make_tenant(slug="other-clinic", name="Other Clinic")
    return client_for(ApiKey.issue(other, "other").raw_key)


def versions_url(agent, suffix=""):
    return f"/v1/agents/{agent.pk}/versions{suffix}"


def create(client, agent, **overrides):
    return client.post(versions_url(agent), {**BODY, **overrides}, format="json")


def test_creating_a_version_makes_a_numbered_draft(client, agent):
    first = create(client, agent)
    second = create(client, agent, system_prompt="Be brief.")

    assert first.status_code == 201
    assert (first.json()["number"], second.json()["number"]) == (1, 2)
    assert first.json()["status"] == "draft"
    assert first.json()["parameters"] == {"temperature": 0.2}


def test_invalid_version_returns_400(client, agent):
    assert create(client, agent, model="nope").status_code == 400
    assert agent.versions.count() == 0


def test_status_and_number_cannot_be_forced(client, agent):
    response = create(client, agent, status="published", number=50)

    assert response.json()["status"] == "draft"
    assert response.json()["number"] == 1


def test_lists_versions_newest_first_and_retrieves_one(client, agent):
    create(client, agent)
    second = create(client, agent).json()

    listing = client.get(versions_url(agent)).json()

    assert [v["number"] for v in listing] == [2, 1]
    assert client.get(versions_url(agent, f"/{second['id']}")).json()["number"] == 2


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_versions_cannot_be_edited_or_deleted(client, agent, method):
    version = create(client, agent).json()
    url = versions_url(agent, f"/{version['id']}")

    response = getattr(client, method)(url, {"system_prompt": "Changed"}, format="json")

    assert response.status_code == 405
    stored = AgentVersion.objects.get(pk=version["id"])
    assert stored.system_prompt == "Be helpful."


def test_published_version_does_not_accept_edits(client, agent):
    version = create(client, agent).json()
    url = versions_url(agent, f"/{version['id']}")
    client.post(f"{url}/publish")

    response = client.patch(url, {"system_prompt": "Changed"}, format="json")

    assert response.status_code == 405
    assert AgentVersion.objects.get(pk=version["id"]).system_prompt == "Be helpful."


def test_publishing_sets_status_and_exposes_it_on_the_agent(client, agent):
    version = create(client, agent).json()

    response = client.post(versions_url(agent, f"/{version['id']}/publish"))

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["published_at"] is not None
    assert client.get(f"/v1/agents/{agent.pk}").json()["published_version"] == 1


def test_publishing_a_new_version_archives_the_previous_one(client, agent):
    first = create(client, agent).json()
    second = create(client, agent).json()
    client.post(versions_url(agent, f"/{first['id']}/publish"))

    client.post(versions_url(agent, f"/{second['id']}/publish"))

    assert client.get(versions_url(agent, f"/{first['id']}")).json()["status"] == "archived"
    assert client.get(f"/v1/agents/{agent.pk}").json()["published_version"] == 2


def test_publishing_twice_returns_409(client, agent):
    version = create(client, agent).json()
    url = versions_url(agent, f"/{version['id']}/publish")
    client.post(url)

    assert client.post(url).status_code == 409


def test_archiving_works_once(client, agent):
    version = create(client, agent).json()
    url = versions_url(agent, f"/{version['id']}/archive")

    assert client.post(url).json()["status"] == "archived"
    assert client.post(url).status_code == 409
    assert client.post(versions_url(agent, f"/{version['id']}/publish")).status_code == 409


def test_other_tenants_cannot_see_or_change_versions(client, other_client, agent):
    version = create(client, agent).json()
    base = versions_url(agent)

    assert other_client.get(base).status_code == 404
    assert other_client.post(base, BODY, format="json").status_code == 404
    assert other_client.get(f"{base}/{version['id']}").status_code == 404
    assert other_client.post(f"{base}/{version['id']}/publish").status_code == 404
    assert AgentVersion.objects.get(pk=version["id"]).status == "draft"


def test_version_must_belong_to_the_agent_in_the_url(client, agent, tenant):
    other_agent = Agent.objects.create(tenant=tenant, name="Sales")
    version = create(client, other_agent).json()

    response = client.get(versions_url(agent, f"/{version['id']}"))

    assert response.status_code == 404


def test_requires_authentication(agent):
    assert APIClient().get(versions_url(agent)).status_code == 401
