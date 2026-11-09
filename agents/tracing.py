import logging
import uuid
from datetime import datetime
from typing import Any, Protocol

import httpx
from django.conf import settings
from django.utils import timezone

from agents.execution import TraceEvent
from agents.models import Run

logger = logging.getLogger(__name__)

INGESTION_PATH = "/api/public/ingestion"
TRACING_TIMEOUT_SECONDS = 5.0


class Tracer(Protocol):
    def trace_run(self, run: Run, events: list[TraceEvent]) -> None: ...


class NullTracer:
    def trace_run(self, run: Run, events: list[TraceEvent]) -> None:
        return None


def iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def run_metadata(run: Run) -> dict[str, Any]:
    version = run.agent_version
    return {
        "tenant_id": str(run.tenant_id),
        "run_id": str(run.id),
        "agent_id": str(version.agent_id),
        "agent_version": version.number,
        "status": run.status,
    }


def envelope(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "type": kind, "timestamp": iso(timezone.now()), "body": body}


def event_body(run: Run, event: TraceEvent) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "traceId": str(run.id),
        "name": event.name,
        "startTime": iso(event.started_at),
        "endTime": iso(event.ended_at),
        "input": event.input,
        "output": event.output,
    }
    if event.error:
        body["level"] = "ERROR"
        body["statusMessage"] = event.error
    if event.kind == "generation":
        body["model"] = event.model
        body["usage"] = {
            "input": event.usage.get("prompt_tokens", 0),
            "output": event.usage.get("completion_tokens", 0),
            "unit": "TOKENS",
        }
    return body


class LangfuseTracer:
    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._auth = (public_key, secret_key)
        self._transport = transport

    def build_batch(self, run: Run, events: list[TraceEvent]) -> list[dict[str, Any]]:
        trace = {
            "id": str(run.id),
            "name": "agent-run",
            "timestamp": iso(run.started_at or run.created_at),
            "userId": str(run.tenant_id),
            "sessionId": str(run.agent_version.agent_id),
            "input": run.input,
            "output": run.output if run.output is not None else {"error": run.error},
            "metadata": run_metadata(run),
            "tags": [run.status],
        }
        batch = [envelope("trace-create", trace)]
        for event in events:
            kind = "generation-create" if event.kind == "generation" else "span-create"
            batch.append(envelope(kind, event_body(run, event)))
        return batch

    def trace_run(self, run: Run, events: list[TraceEvent]) -> None:
        payload = {"batch": self.build_batch(run, events)}
        with httpx.Client(
            timeout=TRACING_TIMEOUT_SECONDS, auth=self._auth, transport=self._transport
        ) as client:
            reply = client.post(f"{self._host}{INGESTION_PATH}", json=payload)
        reply.raise_for_status()
        errors = reply.json().get("errors") or []
        if errors:
            raise RuntimeError(f"Langfuse rejected {len(errors)} events.")


def get_tracer() -> Tracer:
    if settings.LANGFUSE_HOST and settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        return LangfuseTracer(
            settings.LANGFUSE_HOST, settings.LANGFUSE_PUBLIC_KEY, settings.LANGFUSE_SECRET_KEY
        )
    return NullTracer()


def trace_run_safely(run: Run, events: list[TraceEvent]) -> None:
    try:
        get_tracer().trace_run(run, events)
    except Exception:
        logger.warning("run tracing failed", exc_info=True)
