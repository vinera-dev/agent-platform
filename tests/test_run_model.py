import pytest

from agents.models import Agent, InvalidTransition, Run

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(tenant):
    agent = Agent.objects.create(tenant=tenant, name="Support bot")
    return agent.new_version(system_prompt="Be helpful.", model="gpt-4o-mini")


@pytest.fixture
def run(tenant, version):
    return Run.objects.create(tenant=tenant, agent_version=version, input={"message": "hi"})


def test_run_starts_pending_with_no_result(run):
    assert run.status == Run.Status.PENDING
    assert run.output is None
    assert run.error == ""
    assert run.started_at is None
    assert run.finished_at is None
    assert run.duration is None


def test_run_succeeds_through_running(run):
    run.mark_running()
    run.mark_succeeded({"text": "hello"})
    run.refresh_from_db()

    assert run.status == Run.Status.SUCCEEDED
    assert run.output == {"text": "hello"}
    assert run.started_at <= run.finished_at
    assert run.duration is not None


def test_run_can_fail_with_error(run):
    run.mark_running()
    run.mark_failed("provider timeout")
    run.refresh_from_db()

    assert run.status == Run.Status.FAILED
    assert run.error == "provider timeout"
    assert run.finished_at is not None


def test_pending_run_can_fail_before_starting(run):
    run.mark_failed("could not enqueue")

    assert run.status == Run.Status.FAILED


def test_invalid_transitions_are_rejected(run):
    with pytest.raises(InvalidTransition):
        run.mark_succeeded({"text": "x"})

    run.mark_running()
    with pytest.raises(InvalidTransition):
        run.mark_running()

    run.mark_succeeded({"text": "x"})
    with pytest.raises(InvalidTransition):
        run.mark_failed("late")


def test_runs_are_scoped_by_tenant(run, make_tenant):
    other = make_tenant(slug="other-clinic", name="Other")

    assert list(Run.objects.for_tenant(run.tenant)) == [run]
    assert list(Run.objects.for_tenant(other)) == []


def test_version_with_runs_cannot_be_deleted(run, version):
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        version.delete()
