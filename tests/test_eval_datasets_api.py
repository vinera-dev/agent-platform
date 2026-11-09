import pytest
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor

from agents.models import Agent
from evaluation.models import EvalCase, EvalDataset
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


@pytest.fixture
def agent(tenant):
    return Agent.objects.create(tenant=tenant, name="Support")


@pytest.fixture
def dataset(client, agent):
    response = client.post(
        "/v1/eval-datasets", {"name": "Smoke", "agent": str(agent.pk)}, format="json"
    )
    return EvalDataset.objects.get(pk=response.json()["id"])


def case_body(**extra):
    return {
        "input": {"message": "When do you open?"},
        "expected_contains": ["eight"],
        **extra,
    }


def test_migration_is_applied():
    executor = MigrationExecutor(connection)

    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert ("evaluation", "0001_initial") in executor.loader.applied_migrations


def test_creates_a_dataset_for_the_calling_tenant(client, agent, tenant):
    response = client.post(
        "/v1/eval-datasets", {"name": "Smoke", "agent": str(agent.pk)}, format="json"
    )

    body = response.json()
    assert response.status_code == 201
    assert body["case_count"] == 0
    assert EvalDataset.objects.get(pk=body["id"]).tenant == tenant


def test_dataset_cannot_target_another_tenants_agent(client, other_tenant):
    foreign = Agent.objects.create(tenant=other_tenant, name="Foreign")

    response = client.post(
        "/v1/eval-datasets", {"name": "Smoke", "agent": str(foreign.pk)}, format="json"
    )

    assert response.status_code == 400
    assert "agent" in response.json()


def test_dataset_names_are_unique_per_tenant(client, agent, dataset):
    response = client.post(
        "/v1/eval-datasets", {"name": "Smoke", "agent": str(agent.pk)}, format="json"
    )

    assert response.status_code == 400


def test_dataset_crud_round_trip(client, agent, dataset):
    listed = client.get("/v1/eval-datasets").json()
    updated = client.patch(
        f"/v1/eval-datasets/{dataset.pk}", {"description": "Quick checks"}, format="json"
    )
    deleted = client.delete(f"/v1/eval-datasets/{dataset.pk}")

    assert [item["name"] for item in listed] == ["Smoke"]
    assert updated.json()["description"] == "Quick checks"
    assert deleted.status_code == 204
    assert EvalDataset.objects.count() == 0


def test_cases_crud_round_trip(client, dataset):
    base = f"/v1/eval-datasets/{dataset.pk}/cases"

    created = client.post(base, case_body(name="hours"), format="json")
    case_id = created.json()["id"]
    listed = client.get(base).json()
    patched = client.patch(
        f"{base}/{case_id}", {"expected_contains": ["eight", "six"]}, format="json"
    )
    fetched = client.get(f"{base}/{case_id}").json()
    deleted = client.delete(f"{base}/{case_id}")

    assert created.status_code == 201
    assert [item["name"] for item in listed] == ["hours"]
    assert patched.status_code == 200
    assert fetched["expected_contains"] == ["eight", "six"]
    assert deleted.status_code == 204
    assert EvalCase.objects.count() == 0


def test_dataset_reports_its_case_count(client, dataset):
    base = f"/v1/eval-datasets/{dataset.pk}/cases"
    client.post(base, case_body(), format="json")
    client.post(base, case_body(expected_output="We open at eight."), format="json")

    assert client.get(f"/v1/eval-datasets/{dataset.pk}").json()["case_count"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"input": {}, "expected_contains": ["x"]},
        {"input": "text", "expected_contains": ["x"]},
        {"expected_contains": ["x"]},
        {"input": {"message": "hi"}},
        {"input": {"message": "hi"}, "expected_output": "  ", "expected_contains": []},
        {"input": {"message": "hi"}, "expected_contains": [" "]},
        {"input": {"message": "hi"}, "expected_contains": ["x"] * 21},
    ],
)
def test_invalid_cases_are_rejected(client, dataset, payload):
    response = client.post(f"/v1/eval-datasets/{dataset.pk}/cases", payload, format="json")

    assert response.status_code == 400
    assert EvalCase.objects.count() == 0


def test_patching_cannot_leave_a_case_without_expectations(client, dataset):
    base = f"/v1/eval-datasets/{dataset.pk}/cases"
    case_id = client.post(base, case_body(), format="json").json()["id"]

    response = client.patch(f"{base}/{case_id}", {"expected_contains": []}, format="json")

    assert response.status_code == 400


def test_datasets_and_cases_are_isolated_between_tenants(client, other_client, dataset):
    base = f"/v1/eval-datasets/{dataset.pk}/cases"
    case_id = client.post(base, case_body(), format="json").json()["id"]

    assert other_client.get("/v1/eval-datasets").json() == []
    assert other_client.get(f"/v1/eval-datasets/{dataset.pk}").status_code == 404
    assert other_client.get(base).status_code == 404
    assert other_client.post(base, case_body(), format="json").status_code == 404
    assert other_client.get(f"{base}/{case_id}").status_code == 404
    assert other_client.delete(f"{base}/{case_id}").status_code == 404
    assert EvalCase.objects.count() == 1


def test_case_belongs_to_exactly_its_dataset(client, agent, dataset):
    other = client.post(
        "/v1/eval-datasets", {"name": "Other", "agent": str(agent.pk)}, format="json"
    ).json()["id"]
    case_id = client.post(
        f"/v1/eval-datasets/{dataset.pk}/cases", case_body(), format="json"
    ).json()["id"]

    assert client.get(f"/v1/eval-datasets/{other}/cases/{case_id}").status_code == 404


def test_deleting_a_dataset_removes_its_cases(client, dataset):
    client.post(f"/v1/eval-datasets/{dataset.pk}/cases", case_body(), format="json")

    dataset.delete()

    assert EvalCase.objects.count() == 0


def test_database_enforces_unique_dataset_names(tenant, agent):
    EvalDataset.objects.create(tenant=tenant, agent=agent, name="Same")

    with pytest.raises(IntegrityError):
        EvalDataset.objects.create(tenant=tenant, agent=agent, name="Same")


def test_requires_authentication(client_for):
    assert client_for("bad.key").get("/v1/eval-datasets").status_code == 401
