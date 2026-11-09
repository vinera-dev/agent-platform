import pytest

from tenants.models import ApiKey
from tools.models import Tool
from tools.schema import InvalidToolSchema, find_external_references, validate_input_schema

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "properties": {"date": {"type": "string", "format": "date"}, "size": {"type": "integer"}},
    "required": ["date"],
    "additionalProperties": False,
}


def payload(**extra):
    base = {
        "name": "lookup_slots",
        "description": "Find free appointment slots.",
        "input_schema": SCHEMA,
        "endpoint_url": "https://scheduler.example.com/slots",
    }
    return {**base, **extra}


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def other_client(make_tenant, client_for):
    other = make_tenant(slug="other-clinic", name="Other Clinic")
    return client_for(ApiKey.issue(other, "other").raw_key)


def test_registers_a_tool_for_the_calling_tenant(client, tenant):
    response = client.post("/v1/tools", payload(), format="json")

    assert response.status_code == 201
    tool = Tool.objects.get(pk=response.json()["id"])
    assert tool.tenant == tenant
    assert tool.input_schema == SCHEMA
    assert response.json()["is_active"] is True


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"a": {"type": "not-a-type"}}},
        {"type": "object", "required": "date"},
        {"type": "object", "properties": []},
        {"type": "array", "items": {"type": "string"}},
        {"properties": {"a": {"type": "string"}}},
        {"type": "object", "properties": {"a": {"$ref": "https://evil.example.com/schema.json"}}},
        {"type": "object", "properties": {"a": {"$ref": "file:///etc/passwd"}}},
        ["not", "an", "object"],
        "text",
        None,
    ],
)
def test_invalid_schemas_are_rejected(client, schema):
    response = client.post("/v1/tools", payload(input_schema=schema), format="json")

    assert response.status_code == 400
    assert "input_schema" in response.json()
    assert Tool.objects.count() == 0


def test_oversized_schema_is_rejected(client):
    huge = {
        "type": "object",
        "properties": {
            f"field_{n}": {"type": "string", "description": "x" * 50} for n in range(400)
        },
    }

    response = client.post("/v1/tools", payload(input_schema=huge), format="json")

    assert response.status_code == 400


def test_local_references_are_allowed(client):
    schema = {
        "type": "object",
        "$defs": {"slot": {"type": "string"}},
        "properties": {"first": {"$ref": "#/$defs/slot"}},
    }

    assert client.post("/v1/tools", payload(input_schema=schema), format="json").status_code == 201


@pytest.mark.parametrize("name", ["Bad Name", "1abc", "", "a" * 65, "has-dash"])
def test_invalid_names_are_rejected(client, name):
    response = client.post("/v1/tools", payload(name=name), format="json")

    assert response.status_code == 400
    assert "name" in response.json()


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "javascript:alert(1)", "not a url", "https://user:pw@example.com/x"],
)
def test_invalid_endpoints_are_rejected(client, url):
    response = client.post("/v1/tools", payload(endpoint_url=url), format="json")

    assert response.status_code == 400
    assert "endpoint_url" in response.json()


def test_duplicate_names_are_rejected_within_a_tenant_only(client, other_client):
    assert client.post("/v1/tools", payload(), format="json").status_code == 201

    assert client.post("/v1/tools", payload(), format="json").status_code == 400
    assert other_client.post("/v1/tools", payload(), format="json").status_code == 201


def test_update_revalidates_the_schema(client):
    tool_id = client.post("/v1/tools", payload(), format="json").json()["id"]

    bad = client.patch(f"/v1/tools/{tool_id}", {"input_schema": {"type": "array"}}, format="json")
    good = client.patch(f"/v1/tools/{tool_id}", {"description": "Changed."}, format="json")

    assert bad.status_code == 400
    assert good.status_code == 200
    assert Tool.objects.get(pk=tool_id).input_schema == SCHEMA


def test_tools_are_isolated_between_tenants(client, other_client):
    tool_id = client.post("/v1/tools", payload(), format="json").json()["id"]

    assert other_client.get("/v1/tools").json() == []
    assert other_client.get(f"/v1/tools/{tool_id}").status_code == 404
    assert other_client.delete(f"/v1/tools/{tool_id}").status_code == 404
    assert client.delete(f"/v1/tools/{tool_id}").status_code == 204


def test_requires_authentication(client_for):
    assert client_for("bad.key").get("/v1/tools").status_code == 401


def test_validate_input_schema_returns_valid_schemas():
    assert validate_input_schema(SCHEMA) == SCHEMA


def test_validate_input_schema_explains_the_failure():
    with pytest.raises(InvalidToolSchema, match="Not a valid JSON Schema"):
        validate_input_schema({"type": "object", "required": "date"})


def test_find_external_references_walks_nested_structures():
    schema = {"anyOf": [{"$ref": "#/a"}, {"items": [{"$ref": "http://x/y"}]}]}

    assert find_external_references(schema) == ["http://x/y"]


def test_endpoint_outside_the_allow_list_is_rejected(client):
    response = client.post(
        "/v1/tools", payload(endpoint_url="https://collector.evil.net/x"), format="json"
    )

    assert response.status_code == 400
    assert "endpoint_url" in response.json()
    assert Tool.objects.count() == 0
