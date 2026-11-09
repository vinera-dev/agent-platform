from datetime import timedelta

import pytest
from django.utils import timezone

from agents.models import Agent, Run
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def version(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support")
    version = agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini")
    version.publish()
    return version


def make_runs(tenant, version, count, **fields):
    start = timezone.now() - timedelta(hours=1)
    runs = []
    for n in range(count):
        run = Run.objects.create(
            tenant=tenant, agent_version=version, input={"message": str(n)}, **fields
        )
        Run.objects.filter(pk=run.pk).update(created_at=start + timedelta(seconds=n))
        run.refresh_from_db()
        runs.append(run)
    return runs


def test_get_run_returns_its_details(client, tenant, version):
    (run,) = make_runs(tenant, version, 1)
    run.mark_running()
    run.mark_succeeded({"text": "hello"})

    response = client.get(f"/v1/runs/{run.id}")

    body = response.json()
    assert response.status_code == 200
    assert body["id"] == str(run.id)
    assert body["status"] == "succeeded"
    assert body["output"] == {"text": "hello"}
    assert body["agent_id"] == str(version.agent_id)
    assert body["agent_version"] == version.number
    assert body["started_at"] and body["finished_at"]


def test_unknown_run_returns_404(client):
    assert client.get("/v1/runs/00000000-0000-0000-0000-000000000000").status_code == 404


def test_runs_of_other_tenants_are_invisible(client, version, make_tenant, client_for):
    other = make_tenant(slug="other-clinic", name="Other")
    other_agent = Agent.objects.create(tenant=other, name="Other bot")
    other_version = other_agent.new_version(system_prompt="x", model="gpt-4o-mini")
    foreign = make_runs(other, other_version, 1)[0]

    assert client.get(f"/v1/runs/{foreign.id}").status_code == 404
    assert client.get("/v1/runs").json()["count"] == 0
    other_client = client_for(ApiKey.issue(other, "other").raw_key)
    assert other_client.get(f"/v1/runs/{foreign.id}").status_code == 200


def test_list_is_paginated_newest_first(client, tenant, version):
    runs = make_runs(tenant, version, 5)

    first = client.get("/v1/runs?limit=2").json()
    second = client.get("/v1/runs?limit=2&offset=2").json()
    last = client.get("/v1/runs?limit=2&offset=4").json()

    assert first["count"] == 5
    assert first["next"] is not None and first["previous"] is None
    assert [r["id"] for r in first["results"]] == [str(runs[4].id), str(runs[3].id)]
    assert [r["id"] for r in second["results"]] == [str(runs[2].id), str(runs[1].id)]
    assert [r["id"] for r in last["results"]] == [str(runs[0].id)]
    assert last["next"] is None


def test_default_page_size_and_limit_cap(client, tenant, version):
    make_runs(tenant, version, 25)

    assert len(client.get("/v1/runs").json()["results"]) == 20
    assert len(client.get("/v1/runs?limit=1000").json()["results"]) == 25


def test_list_filters_by_status(client, tenant, version):
    make_runs(tenant, version, 2)
    make_runs(tenant, version, 1, status=Run.Status.FAILED, error="x")

    failed = client.get("/v1/runs?status=failed").json()

    assert failed["count"] == 1
    assert failed["results"][0]["status"] == "failed"


def test_list_filters_by_agent(client, tenant, version):
    other_agent = Agent.objects.create(tenant=tenant, name="Sales")
    other_version = other_agent.new_version(system_prompt="x", model="gpt-4o-mini")
    make_runs(tenant, version, 2)
    make_runs(tenant, other_version, 1)

    response = client.get(f"/v1/runs?agent={other_agent.id}").json()

    assert response["count"] == 1
    assert response["results"][0]["agent_id"] == str(other_agent.id)


@pytest.mark.parametrize("query", ["status=unknown", "agent=not-a-uuid"])
def test_invalid_filters_return_400(client, query):
    assert client.get(f"/v1/runs?{query}").status_code == 400


def test_runs_are_read_only(client, tenant, version):
    (run,) = make_runs(tenant, version, 1)

    assert client.delete(f"/v1/runs/{run.id}").status_code == 405
    assert (
        client.patch(f"/v1/runs/{run.id}", {"status": "failed"}, format="json").status_code == 405
    )
    assert client.post("/v1/runs", {}, format="json").status_code == 405


def test_runs_require_authentication():
    from rest_framework.test import APIClient

    assert APIClient().get("/v1/runs").status_code in (401, 403)
