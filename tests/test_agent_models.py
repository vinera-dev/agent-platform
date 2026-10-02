import pytest
from django.db import IntegrityError, transaction

from agents.models import Agent, AgentVersion

pytestmark = pytest.mark.django_db

VERSION_FIELDS = {"system_prompt": "You are a helpful assistant.", "model": "gpt-4o-mini"}


@pytest.fixture
def agent(tenant):
    return Agent.objects.create(tenant=tenant, name="Support bot")


def test_creates_an_agent_for_a_tenant(agent, tenant):
    assert agent.tenant == tenant
    assert str(agent) == "Support bot"
    assert list(tenant.agents.all()) == [agent]


def test_agent_name_is_unique_per_tenant(agent, tenant, make_tenant):
    with pytest.raises(IntegrityError), transaction.atomic():
        Agent.objects.create(tenant=tenant, name="Support bot")

    other = make_tenant(slug="other-clinic", name="Other")
    assert Agent.objects.create(tenant=other, name="Support bot").pk != agent.pk


def test_versions_are_numbered_sequentially(agent):
    first = agent.new_version(**VERSION_FIELDS)
    second = agent.new_version(**VERSION_FIELDS)

    assert (first.number, second.number) == (1, 2)
    assert first.status == AgentVersion.Status.DRAFT


def test_version_numbers_are_independent_per_agent(agent, tenant):
    other = Agent.objects.create(tenant=tenant, name="Sales bot")
    agent.new_version(**VERSION_FIELDS)
    agent.new_version(**VERSION_FIELDS)

    assert other.new_version(**VERSION_FIELDS).number == 1


def test_version_defaults(agent):
    version = agent.new_version(**VERSION_FIELDS)

    assert version.parameters == {}
    assert version.tools == []
    assert version.published_at is None


def test_version_stores_parameters_and_tools(agent):
    version = agent.new_version(
        **VERSION_FIELDS, parameters={"temperature": 0.2}, tools=["lookup_slots"]
    )
    version.refresh_from_db()

    assert version.parameters == {"temperature": 0.2}
    assert version.tools == ["lookup_slots"]


def test_only_one_version_can_be_published(agent):
    first = agent.new_version(**VERSION_FIELDS)
    second = agent.new_version(**VERSION_FIELDS)
    first.publish()

    with pytest.raises(IntegrityError), transaction.atomic():
        second.publish()


def test_publish_sets_status_and_timestamp(agent):
    version = agent.new_version(**VERSION_FIELDS)

    version.publish()
    version.refresh_from_db()

    assert version.status == AgentVersion.Status.PUBLISHED
    assert version.published_at is not None


def test_deleting_an_agent_removes_its_versions(agent):
    agent.new_version(**VERSION_FIELDS)

    agent.delete()

    assert AgentVersion.objects.count() == 0
