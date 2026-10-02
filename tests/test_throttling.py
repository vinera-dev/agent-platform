import pytest
from rest_framework.test import APIClient

from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def small_limit(settings):
    settings.TENANT_RATE_LIMIT = "3/min"


def test_requests_above_the_limit_get_429(issued_key, client_for):
    client = client_for(issued_key.raw_key)

    statuses = [client.get("/v1/whoami").status_code for _ in range(5)]

    assert statuses == [200, 200, 200, 429, 429]


def test_429_carries_retry_after(issued_key, client_for):
    client = client_for(issued_key.raw_key)
    for _ in range(3):
        client.get("/v1/whoami")

    response = client.get("/v1/whoami")

    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0


def test_limit_is_shared_by_all_keys_of_a_tenant(tenant, issued_key, client_for):
    second = ApiKey.issue(tenant, "second")
    first_client = client_for(issued_key.raw_key)
    second_client = client_for(second.raw_key)

    for _ in range(3):
        first_client.get("/v1/whoami")

    assert second_client.get("/v1/whoami").status_code == 429


def test_tenants_do_not_share_a_budget(issued_key, make_tenant, client_for):
    other = ApiKey.issue(make_tenant(slug="other-clinic", name="Other"), "key")
    busy = client_for(issued_key.raw_key)
    for _ in range(4):
        busy.get("/v1/whoami")

    assert client_for(other.raw_key).get("/v1/whoami").status_code == 200


def test_failed_authentication_does_not_consume_a_tenant_budget(issued_key, client_for):
    anonymous = APIClient()
    for _ in range(5):
        assert anonymous.get("/v1/whoami").status_code == 401

    assert client_for(issued_key.raw_key).get("/v1/whoami").status_code == 200


def test_health_is_not_throttled():
    client = APIClient()

    assert all(client.get("/health").status_code == 200 for _ in range(6))
