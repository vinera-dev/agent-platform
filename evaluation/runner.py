import re
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone

from agents.execution import ExecutionError, generate
from agents.models import AgentVersion
from agents.providers import LLMProvider, ProviderError
from evaluation.models import EvalCase, EvalDataset

TRIM = " \t\r\n.,;:!?\"'"
WHITESPACE = re.compile(r"\s+")


class EvaluationError(Exception):
    pass


def normalize(text: str) -> str:
    return WHITESPACE.sub(" ", text.casefold()).strip(TRIM)


@dataclass
class CaseResult:
    case_id: str
    name: str
    input: dict[str, Any]
    expected_output: str
    expected_contains: list[str]
    actual_output: str = ""
    exact_match: bool | None = None
    contains_found: list[str] = field(default_factory=list)
    contains_score: float | None = None
    passed: bool = False
    error: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    judge_score: int | None = None
    judge_justification: str = ""


@dataclass
class EvalReport:
    dataset_id: str
    dataset_name: str
    agent_version: int
    provider: str
    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def errors(self) -> int:
        return sum(1 for result in self.results if result.error)

    @property
    def accuracy(self) -> float:
        return round(self.passed / self.total, 4) if self.total else 0.0

    @property
    def exact_match_rate(self) -> float | None:
        scored = [result.exact_match for result in self.results if result.exact_match is not None]
        return round(sum(scored) / len(scored), 4) if scored else None

    @property
    def content_score(self) -> float | None:
        scored = [r.contains_score for r in self.results if r.contains_score is not None]
        return round(sum(scored) / len(scored), 4) if scored else None

    @property
    def judge_average(self) -> float | None:
        scored = [r.judge_score for r in self.results if r.judge_score is not None]
        return round(sum(scored) / len(scored), 4) if scored else None

    def metrics(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "errors": self.errors,
            "accuracy": self.accuracy,
            "exact_match_rate": self.exact_match_rate,
            "content_score": self.content_score,
            "judge_average": self.judge_average,
        }


def score_case(case: EvalCase, actual: str) -> dict[str, Any]:
    outcome: dict[str, Any] = {}
    checks: list[bool] = []
    if case.expected_output.strip():
        outcome["exact_match"] = normalize(actual) == normalize(case.expected_output)
        checks.append(outcome["exact_match"])
    if case.expected_contains:
        haystack = normalize(actual)
        found = [item for item in case.expected_contains if normalize(item) in haystack]
        outcome["contains_found"] = found
        outcome["contains_score"] = round(len(found) / len(case.expected_contains), 4)
        checks.append(len(found) == len(case.expected_contains))
    outcome["passed"] = bool(checks) and all(checks)
    return outcome


def resolve_version(dataset: EvalDataset, version: AgentVersion | None) -> AgentVersion:
    if version is not None:
        if version.agent_id != dataset.agent_id:
            raise EvaluationError("The version belongs to a different agent.")
        return version
    published = dataset.agent.versions.filter(status=AgentVersion.Status.PUBLISHED).first()
    if published is None:
        raise EvaluationError("The agent has no published version to evaluate.")
    return published


def evaluate_case(case: EvalCase, version: AgentVersion, provider: LLMProvider) -> CaseResult:
    result = CaseResult(
        case_id=str(case.id),
        name=case.name,
        input=case.input,
        expected_output=case.expected_output,
        expected_contains=list(case.expected_contains),
    )
    started = timezone.now()
    try:
        generated = generate(
            tenant=case.tenant,
            version=version,
            user_input=case.input,
            provider=provider,
            timeout=settings.RUN_TIMEOUT_SECONDS,
        )
    except (ProviderError, ExecutionError) as error:
        result.error = str(error)
    else:
        result.actual_output = generated.text
        result.prompt_tokens = generated.usage.get("prompt_tokens", 0)
        result.completion_tokens = generated.usage.get("completion_tokens", 0)
        for key, value in score_case(case, generated.text).items():
            setattr(result, key, value)
    result.latency_ms = int((timezone.now() - started).total_seconds() * 1000)
    return result


def run_dataset(
    dataset: EvalDataset,
    provider: LLMProvider,
    *,
    provider_name: str = "",
    version: AgentVersion | None = None,
) -> EvalReport:
    version = resolve_version(dataset, version)
    cases = dataset.cases.select_related("tenant").order_by("created_at", "id")
    results = [evaluate_case(case, version, provider) for case in cases]
    return EvalReport(
        dataset_id=str(dataset.id),
        dataset_name=dataset.name,
        agent_version=version.number,
        provider=provider_name,
        results=results,
    )
