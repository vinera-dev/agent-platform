from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Q, QuerySet, Sum

from agents.models import Run


def day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def filter_period(runs: QuerySet[Run], start: date | None, end: date | None) -> QuerySet[Run]:
    if start is not None:
        runs = runs.filter(created_at__gte=day_start(start))
    if end is not None:
        runs = runs.filter(created_at__lt=day_start(end + timedelta(days=1)))
    return runs


AGGREGATES = {
    "runs": Count("id"),
    "succeeded": Count("id", filter=Q(status=Run.Status.SUCCEEDED)),
    "failed": Count("id", filter=Q(status=Run.Status.FAILED)),
    "prompt_tokens": Sum("prompt_tokens"),
    "completion_tokens": Sum("completion_tokens"),
    "estimated_cost_usd": Sum("estimated_cost_usd"),
    "average_latency_ms": Avg("latency_ms"),
}


def shape(row: dict[str, Any]) -> dict[str, Any]:
    prompt = row["prompt_tokens"] or 0
    completion = row["completion_tokens"] or 0
    latency = row["average_latency_ms"]
    return {
        "runs": row["runs"],
        "succeeded": row["succeeded"],
        "failed": row["failed"],
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated_cost_usd": str(
            (row["estimated_cost_usd"] or Decimal(0)).quantize(Decimal("0.000001"))
        ),
        "average_latency_ms": round(latency, 1) if latency is not None else None,
    }


def summarize(runs: QuerySet[Run]) -> dict[str, Any]:
    totals = shape(runs.aggregate(**AGGREGATES))
    grouped = (
        runs.values("agent_version__agent_id", "agent_version__agent__name")
        .annotate(**AGGREGATES)
        .order_by("agent_version__agent__name", "agent_version__agent_id")
    )
    by_agent = [
        {
            "agent_id": str(row["agent_version__agent_id"]),
            "agent_name": row["agent_version__agent__name"],
            **shape(row),
        }
        for row in grouped
    ]
    return {"totals": totals, "by_agent": by_agent}
