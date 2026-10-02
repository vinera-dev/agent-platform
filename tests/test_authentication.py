import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_valid_key_identifies_the_tenant(issued_key, client_for, tenant):
    response = client_for(issued_key.raw_key).get("/v1/whoami")

    assert response.status_code == 200
    assert response.json()["tenant"]["slug"] == tenant.slug


def test_valid_key_records_last_use(issued_key, client_for):
    assert issued_key.api_key.last_used_at is None

    client_for(issued_key.raw_key).get("/v1/whoami")
    issued_key.api_key.refresh_from_db()

    assert issued_key.api_key.last_used_at is not None


def test_missing_header_is_rejected():
    response = APIClient().get("/v1/whoami")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Api-Key"


@pytest.mark.parametrize(
    "header",
    [
        "Api-Key",
        "Api-Key a b",
        "Bearer abc",
        "Api-Key 00000000.nope",
        "Api-Key garbage",
    ],
)
def test_malformed_or_unknown_credentials_are_rejected(header):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=header)

    assert client.get("/v1/whoami").status_code == 401


def test_revoked_key_is_rejected(issued_key, client_for):
    issued_key.api_key.revoke()

    assert client_for(issued_key.raw_key).get("/v1/whoami").status_code == 401


def test_key_of_inactive_tenant_is_rejected(issued_key, client_for, tenant):
    tenant.is_active = False
    tenant.save()

    assert client_for(issued_key.raw_key).get("/v1/whoami").status_code == 401


def test_keyword_is_case_insensitive(issued_key):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"api-key {issued_key.raw_key}")

    assert client.get("/v1/whoami").status_code == 200


def test_health_stays_public():
    assert APIClient().get("/health").status_code == 200
