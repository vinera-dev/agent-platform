from datetime import UTC, datetime
from decimal import Decimal

import pytest

from agents.models import Agent, Run
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def other_tenant(make_tenant):
    return make_tenant(slug="other-clinic", name="Other Clinic")


def make_agent(tenant, name, model="gpt-4o-mini"):
    agent = Agent.objects.create(tenant=tenant, name=name)
    version = agent.new_version(system_prompt="Hi.", model=model)
    version.publish()
    return version


def add_run(tenant, version, *, prompt=0, completion=0, latency=None, status="succeeded", day=None):
    run = Run.objects.create(
        tenant=tenant,
        agent_version=version,
        input={"message": "x"},
        status=status,
        prompt_tokens=prompt,
        completion_tokens=completion,
        latency_ms=latency,
        estimated_cost_usd=Decimal(prompt + completion) / Decimal(1_000_000),
    )
    if day:
        Run.objects.filter(pk=run.pk).update(created_at=day)
    return run


@pytest.fixture
def seeded(tenant, other_tenant):
    support = make_agent(tenant, "Support")
    triage = make_agent(tenant, "Triage")
    foreign = make_agent(other_tenant, "Foreign")
    add_run(tenant, support, prompt=1000, completion=500, latency=100)
    add_run(tenant, support, prompt=2000, completion=1000, latency=300)
    add_run(tenant, triage, prompt=10, completion=5, latency=50)
    add_run(tenant, triage, status="failed", latency=20)
    add_run(other_tenant, foreign, prompt=999_999, completion=999_999, latency=1)
    return support, triage


def test_totals_match_the_runs(client, seeded):
    body = client.get("/v1/usage").json()

    assert body["totals"] == {
        "runs": 4,
        "succeeded": 3,
        "failed": 1,
        "prompt_tokens": 3010,
        "completion_tokens": 1505,
        "total_tokens": 4515,
        "estimated_cost_usd": "0.004515",
        "average_latency_ms": 117.5,
    }
    assert body["totals"]["total_tokens"] == sum(
        run.prompt_tokens + run.completion_tokens
        for run in Run.objects.filter(tenant__slug="acme-vet")
    )


def test_usage_is_broken_down_by_agent(client, seeded):
    support, triage = seeded

    by_agent = client.get("/v1/usage").json()["by_agent"]

    assert [(row["agent_name"], row["runs"], row["total_tokens"]) for row in by_agent] == [
        ("Support", 2, 4500),
        ("Triage", 2, 15),
    ]
    assert by_agent[0]["agent_id"] == str(support.agent_id)
    assert by_agent[0]["average_latency_ms"] == 200.0
    assert by_agent[0]["estimated_cost_usd"] == "0.004500"


def test_other_tenants_runs_never_leak_in(client, seeded):
    body = client.get("/v1/usage").json()

    assert body["totals"]["prompt_tokens"] == 3010
    assert "Foreign" not in str(body)


def test_each_tenant_sees_its_own_usage(other_tenant, client_for, seeded):
    other = client_for(ApiKey.issue(other_tenant, "other").raw_key)

    body = other.get("/v1/usage").json()

    assert body["totals"]["runs"] == 1
    assert body["totals"]["prompt_tokens"] == 999_999


def test_a_tenant_without_runs_gets_zeros(client):
    body = client.get("/v1/usage").json()

    assert body["totals"] == {
        "runs": 0,
        "succeeded": 0,
        "failed": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": "0.000000",
        "average_latency_ms": None,
    }
    assert body["by_agent"] == []


def test_the_period_filters_by_creation_day(client, tenant):
    version = make_agent(tenant, "Support")
    add_run(tenant, version, prompt=100, day=datetime(2026, 1, 10, 23, 59, tzinfo=UTC))
    add_run(tenant, version, prompt=200, day=datetime(2026, 1, 11, 0, 0, tzinfo=UTC))
    add_run(tenant, version, prompt=400, day=datetime(2026, 1, 12, 12, 0, tzinfo=UTC))

    only_eleventh = client.get("/v1/usage?from=2026-01-11&to=2026-01-11").json()
    from_eleventh = client.get("/v1/usage?from=2026-01-11").json()
    until_tenth = client.get("/v1/usage?to=2026-01-10").json()

    assert only_eleventh["totals"]["prompt_tokens"] == 200
    assert only_eleventh["period"] == {"from": "2026-01-11", "to": "2026-01-11"}
    assert from_eleventh["totals"]["prompt_tokens"] == 600
    assert until_tenth["totals"]["prompt_tokens"] == 100


@pytest.mark.parametrize(
    "query", ["from=yesterday", "to=2026-13-01", "from=2026-02-01&to=2026-01-01"]
)
def test_bad_periods_are_rejected(client, query):
    assert client.get(f"/v1/usage?{query}").status_code == 400


def test_usage_requires_authentication(client_for):
    assert client_for("bad.key").get("/v1/usage").status_code == 401
