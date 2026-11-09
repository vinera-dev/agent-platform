import pytest

from agents.models import Agent
from agents.providers import (
    Completion,
    ExtractiveFakeProvider,
    FakeProvider,
    ProviderError,
    get_provider,
)
from evaluation.models import EvalCase, EvalDataset
from evaluation.runner import EvaluationError, normalize, run_dataset, score_case
from knowledge.ingestion import ingest_document
from knowledge.models import Document, KnowledgeBase

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(tenant):
    return Agent.objects.create(tenant=tenant, name="Support")


@pytest.fixture
def published(agent):
    version = agent.new_version(system_prompt="Answer briefly.", model="gpt-4o-mini")
    version.publish()
    return version


@pytest.fixture
def dataset(tenant, agent):
    return EvalDataset.objects.create(tenant=tenant, agent=agent, name="Smoke")


def add_case(dataset, **extra):
    fields = {"tenant": dataset.tenant, "dataset": dataset, "input": {"message": "q"}}
    return EvalCase.objects.create(**{**fields, **extra})


def reply(text):
    return Completion(text, usage={"prompt_tokens": 3, "completion_tokens": 2})


def test_normalization_ignores_case_spacing_and_edge_punctuation():
    assert normalize("  We OPEN   at eight!\n") == "we open at eight"


def test_exact_match_and_content_checks_are_scored_separately(dataset):
    case = add_case(
        dataset, expected_output="We open at eight.", expected_contains=["eight", "six"]
    )

    scored = score_case(case, "we open at eight")

    assert scored == {
        "exact_match": True,
        "contains_found": ["eight"],
        "contains_score": 0.5,
        "passed": False,
    }


def test_a_case_with_only_content_checks_has_no_exact_metric(dataset):
    case = add_case(dataset, expected_contains=["Eight"])

    assert score_case(case, "Open at eight") == {
        "contains_found": ["Eight"],
        "contains_score": 1.0,
        "passed": True,
    }


def test_report_computes_accuracy_and_metrics(dataset, published):
    add_case(dataset, name="exact-ok", expected_output="Yes.")
    add_case(dataset, name="exact-bad", expected_output="Yes.")
    add_case(dataset, name="contains-ok", expected_contains=["alpha", "beta"])
    add_case(dataset, name="contains-half", expected_contains=["alpha", "beta"])
    provider = FakeProvider(
        script=[reply("yes"), reply("no"), reply("alpha and beta"), reply("only alpha")]
    )

    report = run_dataset(dataset, provider, provider_name="fake")

    assert {r.name: r.passed for r in report.results} == {
        "exact-ok": True,
        "exact-bad": False,
        "contains-ok": True,
        "contains-half": False,
    }
    assert report.metrics() == {
        "total": 4,
        "passed": 2,
        "errors": 0,
        "accuracy": 0.5,
        "exact_match_rate": 0.5,
        "content_score": 0.75,
        "judge_average": None,
    }
    assert report.agent_version == published.number
    assert report.results[0].prompt_tokens == 3
    assert report.results[0].actual_output == "yes"


def test_provider_errors_count_as_failed_cases_without_aborting(dataset, published):
    add_case(dataset, name="boom", expected_contains=["x"])
    add_case(dataset, name="fine", expected_contains=["x"])
    provider = FakeProvider(failures=[ProviderError("rate limited")], script=[reply("x")])

    report = run_dataset(dataset, provider)

    assert [r.error for r in report.results] == ["rate limited", ""]
    assert report.errors == 1
    assert report.accuracy == 0.5


def test_empty_dataset_reports_zero_accuracy(dataset, published):
    report = run_dataset(dataset, FakeProvider())

    assert report.total == 0
    assert report.accuracy == 0.0
    assert report.exact_match_rate is None


def test_agent_without_a_published_version_cannot_be_evaluated(dataset, agent):
    agent.new_version(system_prompt="Draft.", model="gpt-4o-mini")

    with pytest.raises(EvaluationError, match="no published version"):
        run_dataset(dataset, FakeProvider())


def test_a_draft_version_can_be_evaluated_explicitly(dataset, published, agent):
    draft = agent.new_version(system_prompt="Draft prompt.", model="gpt-4o-mini")
    add_case(dataset, expected_contains=["x"])
    provider = FakeProvider(script=[reply("x")])

    report = run_dataset(dataset, provider, version=draft)

    assert report.agent_version == draft.number
    assert provider.calls[0]["system_prompt"] == "Draft prompt."


def test_a_version_of_another_agent_is_rejected(dataset, tenant):
    other = Agent.objects.create(tenant=tenant, name="Other").new_version(
        system_prompt="x", model="gpt-4o-mini"
    )

    with pytest.raises(EvaluationError, match="different agent"):
        run_dataset(dataset, FakeProvider(), version=other)


def test_extractive_provider_answers_from_the_retrieved_context(tenant, dataset, agent, settings):
    settings.RETRIEVAL_MIN_SCORE = 0.0
    base = KnowledgeBase.objects.create(tenant=tenant, name="FAQ")
    content = (
        "The clinic opens at eight in the morning. Puppy vaccines are given at eight weeks. "
        "Free parking is behind the building."
    )
    document = Document.objects.create(
        tenant=tenant,
        knowledge_base=base,
        title="FAQ",
        content=content,
        size_bytes=len(content),
        content_sha256="0" * 64,
    )
    ingest_document(document)
    agent.new_version(system_prompt="Answer.", model="gpt-4o-mini", knowledge_base=base).publish()
    add_case(
        dataset, input={"message": "Where can I park?"}, expected_contains=["behind the building"]
    )
    add_case(dataset, input={"message": "zzzz qqqq"}, expected_output="I do not know.")

    report = run_dataset(dataset, ExtractiveFakeProvider(), provider_name="extractive-fake")

    assert [r.actual_output for r in report.results] == [
        "Free parking is behind the building.",
        "I do not know.",
    ]
    assert report.accuracy == 1.0


def test_extractive_provider_is_deterministic():
    call = {
        "model": "m",
        "system_prompt": '<source id="1" title="t" position="0">\nCats purr. Dogs bark loudly.\n</source>',
        "user_input": {"message": "Do dogs bark?"},
        "parameters": {},
        "timeout": 1.0,
    }

    first = ExtractiveFakeProvider().complete(**call)
    second = ExtractiveFakeProvider().complete(**call)

    assert first == second
    assert first.text == "Dogs bark loudly."


def test_get_provider_resolves_names_explicitly(settings):
    settings.LLM_PROVIDER = "azure"

    assert isinstance(get_provider("extractive-fake"), ExtractiveFakeProvider)
