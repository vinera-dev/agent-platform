import pytest

from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_tenant(make_tenant):
    return make_tenant(slug="other-clinic", name="Other Clinic")


def test_each_tenant_lists_only_its_own_keys(tenant, other_tenant, client_for):
    mine = ApiKey.issue(tenant, "mine")
    ApiKey.issue(tenant, "mine-2")
    theirs = ApiKey.issue(other_tenant, "theirs")

    own = client_for(mine.raw_key).get("/v1/api-keys").json()
    foreign = client_for(theirs.raw_key).get("/v1/api-keys").json()

    assert {item["name"] for item in own} == {"mine", "mine-2"}
    assert [item["name"] for item in foreign] == ["theirs"]


def test_listing_never_exposes_secrets(issued_key, client_for):
    body = client_for(issued_key.raw_key).get("/v1/api-keys").json()

    assert set(body[0]) == {"id", "name", "prefix", "created_at", "last_used_at", "revoked_at"}
    assert issued_key.raw_key not in str(body)


def test_for_tenant_filters_the_queryset(tenant, other_tenant):
    ApiKey.issue(tenant, "a")
    ApiKey.issue(other_tenant, "b")

    assert [key.name for key in ApiKey.objects.for_tenant(tenant)] == ["a"]
    assert [key.name for key in ApiKey.objects.for_tenant(other_tenant)] == ["b"]


def test_listing_requires_authentication(client):
    assert client.get("/v1/api-keys").status_code == 401
