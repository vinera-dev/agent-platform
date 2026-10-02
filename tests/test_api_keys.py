import pytest
from django.db import connection

from tenants.models import ApiKey, Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Acme Vet", slug="acme-vet")


def test_issue_returns_the_raw_key_once(tenant):
    issued = ApiKey.issue(tenant, "backend")

    assert issued.raw_key.startswith(f"{issued.api_key.prefix}.")
    assert issued.api_key.tenant == tenant
    assert issued.api_key.is_active


def test_raw_key_is_never_stored(tenant):
    issued = ApiKey.issue(tenant, "backend")
    secret = issued.raw_key.partition(".")[2]

    with connection.cursor() as cursor:
        cursor.execute("SELECT prefix, key_hash, name FROM tenants_apikey")
        stored = " ".join(str(value) for row in cursor.fetchall() for value in row)

    assert secret not in stored
    assert issued.raw_key not in stored
    assert len(issued.api_key.key_hash) == 64


def test_each_key_is_unique(tenant):
    first = ApiKey.issue(tenant, "a")
    second = ApiKey.issue(tenant, "b")

    assert first.raw_key != second.raw_key
    assert first.api_key.prefix != second.api_key.prefix
    assert first.api_key.key_hash != second.api_key.key_hash


def test_find_by_raw_key_resolves_the_key(tenant):
    issued = ApiKey.issue(tenant, "backend")

    assert ApiKey.find_by_raw_key(issued.raw_key) == issued.api_key


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw + "x",
        lambda raw: raw[:-1] + ("A" if raw[-1] != "A" else "B"),
        lambda raw: raw.partition(".")[0],
        lambda raw: raw.replace(".", ""),
        lambda raw: "",
        lambda raw: "zzzzzzzz." + raw.partition(".")[2],
    ],
)
def test_find_by_raw_key_rejects_tampered_keys(tenant, mutate):
    issued = ApiKey.issue(tenant, "backend")

    assert ApiKey.find_by_raw_key(mutate(issued.raw_key)) is None


def test_revoke_marks_the_key_inactive(tenant):
    issued = ApiKey.issue(tenant, "backend")

    issued.api_key.revoke()
    issued.api_key.refresh_from_db()

    assert issued.api_key.revoked_at is not None
    assert not issued.api_key.is_active
