import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_schema_is_public_and_describes_the_api():
    response = APIClient().get("/v1/schema?format=json")

    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "Agent Platform API"
    assert "/v1/agents" in body["paths"]
    assert "/v1/whoami" in body["paths"]
    assert "ApiKeyAuth" in body["components"]["securitySchemes"]


def test_docs_page_opens_without_credentials():
    response = APIClient().get("/v1/docs")

    assert response.status_code == 200
    assert b"swagger" in response.content.lower()


def test_schema_generation_has_no_warnings(tmp_path):
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yml")
    )


def test_publish_and_archive_take_no_request_body():
    paths = APIClient().get("/v1/schema?format=json").json()["paths"]

    for action in ("publish", "archive"):
        operation = paths[f"/v1/agents/{{agent_id}}/versions/{{id}}/{action}"]["post"]
        assert "requestBody" not in operation
