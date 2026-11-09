import pytest
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor

from tools.models import Tool

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "properties": {"date": {"type": "string"}},
    "required": ["date"],
}


def make_tool(tenant, **extra):
    fields = {
        "tenant": tenant,
        "name": "lookup_slots",
        "description": "Find free appointment slots.",
        "input_schema": SCHEMA,
        "endpoint_url": "https://scheduler.example.com/slots",
    }
    return Tool.objects.create(**{**fields, **extra})


def test_migration_is_applied():
    executor = MigrationExecutor(connection)

    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert ("tools", "0001_initial") in executor.loader.applied_migrations


def test_tool_stores_its_schema(tenant):
    tool = make_tool(tenant)
    tool.refresh_from_db()

    assert tool.input_schema == SCHEMA
    assert tool.is_active is True
    assert str(tool) == "lookup_slots"


def test_names_are_unique_per_tenant(tenant, make_tenant):
    make_tool(tenant)
    make_tool(make_tenant(slug="other", name="Other"))

    with pytest.raises(IntegrityError):
        make_tool(tenant)


def test_for_tenant_scopes_the_queryset(tenant, make_tenant):
    other = make_tenant(slug="other", name="Other")
    make_tool(tenant, name="mine")
    make_tool(other, name="theirs")

    assert [tool.name for tool in Tool.objects.for_tenant(tenant)] == ["mine"]


def test_deleting_a_tenant_removes_its_tools(tenant):
    make_tool(tenant)

    tenant.delete()

    assert Tool.objects.count() == 0
