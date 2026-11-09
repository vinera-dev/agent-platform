import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from agents.models import AgentVersion
from agents.prompting import build_system_prompt
from agents.providers import Completion, LLMProvider, ToolCall, user_message
from knowledge.search import SearchHit, search_chunks
from tenants.models import Tenant
from tools.executor import ToolExecutionError, execute_tool
from tools.models import Tool

SNIPPET_LENGTH = 200

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    pass


class RetrievalFailed(ExecutionError):
    pass


class ToolStepLimitExceeded(ExecutionError):
    pass


@dataclass
class TraceEvent:
    kind: str
    name: str
    started_at: datetime
    ended_at: datetime
    input: Any = None
    output: Any = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""


@dataclass
class ExecutionResult:
    text: str
    usage: dict[str, int]
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    completions: int = 0

    def as_output(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "usage": self.usage,
            "sources": self.sources,
            "tool_calls": self.tool_calls,
        }


def source_payload(hit: SearchHit) -> dict[str, Any]:
    return {
        "document_id": hit.document_id,
        "document_title": hit.document_title,
        "chunk_id": hit.chunk_id,
        "position": hit.position,
        "score": hit.score,
        "snippet": hit.text[:SNIPPET_LENGTH],
    }


def retrieve_context(tenant: Tenant, version: AgentVersion, user_input: dict) -> list[SearchHit]:
    if version.knowledge_base_id is None:
        return []
    try:
        hits = search_chunks(
            tenant,
            user_message(user_input),
            knowledge_base=version.knowledge_base,
            limit=settings.RETRIEVAL_TOP_K,
        )
    except Exception as error:
        raise RetrievalFailed(str(error)) from error
    return [hit for hit in hits if hit.score >= settings.RETRIEVAL_MIN_SCORE]


def load_tools(tenant: Tenant, version: AgentVersion) -> dict[str, Tool]:
    if not version.tools:
        return {}
    found = Tool.objects.for_tenant(tenant).filter(name__in=version.tools, is_active=True)
    return {tool.name: tool for tool in found}


def tool_spec(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }


def assistant_message(completion: Completion) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": completion.text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in completion.tool_calls
        ],
    }


def timed_tool_call(
    call: ToolCall, tools: dict[str, Tool], events: list[TraceEvent] | None
) -> dict[str, Any]:
    started_at = timezone.now()
    record = run_tool_call(call, tools)
    logger.info("tool call", extra={"tool": call.name, "ok": record["ok"]})
    if events is not None:
        events.append(
            TraceEvent(
                kind="tool",
                name=call.name,
                started_at=started_at,
                ended_at=timezone.now(),
                input=call.arguments,
                output=record.get("result"),
                error=record.get("error", ""),
            )
        )
    return record


def run_tool_call(call: ToolCall, tools: dict[str, Tool]) -> dict[str, Any]:
    record: dict[str, Any] = {"name": call.name, "arguments": call.arguments}
    tool = tools.get(call.name)
    if tool is None:
        return {**record, "ok": False, "error": f"Unknown tool: {call.name}."}
    try:
        result = execute_tool(tool, call.arguments)
    except ToolExecutionError as error:
        return {**record, "ok": False, "error": str(error)}
    return {**record, "ok": True, "result": result}


def tool_message(call: ToolCall, record: dict[str, Any]) -> dict[str, Any]:
    payload = {"result": record["result"]} if record["ok"] else {"error": record["error"]}
    return {"role": "tool", "tool_call_id": call.id, "content": json.dumps(payload)}


def generation_event(
    version: AgentVersion,
    user_input: dict,
    history: list[dict[str, Any]],
    started_at: datetime,
    completion: Completion | None = None,
    error: str = "",
) -> TraceEvent:
    output = None
    if completion is not None:
        output = {
            "text": completion.text,
            "tool_calls": [
                {"name": call.name, "arguments": call.arguments} for call in completion.tool_calls
            ],
        }
    return TraceEvent(
        kind="generation",
        name="llm-call",
        started_at=started_at,
        ended_at=timezone.now(),
        input={"input": user_input, "history": list(history)},
        output=output,
        model=version.model,
        usage=dict(completion.usage) if completion is not None else {},
        error=error,
    )


def generate(
    *,
    tenant: Tenant,
    version: AgentVersion,
    user_input: dict,
    provider: LLMProvider,
    timeout: float,
    events: list[TraceEvent] | None = None,
) -> ExecutionResult:
    hits = retrieve_context(tenant, version, user_input)
    system_prompt = build_system_prompt(version.system_prompt, hits)
    tools = load_tools(tenant, version)
    specs = [tool_spec(tool) for tool in tools.values()]
    history: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    usage: Counter[str] = Counter()
    for round_number in range(settings.MAX_TOOL_STEPS + 1):
        started_at = timezone.now()
        try:
            completion = provider.complete(
                model=version.model,
                system_prompt=system_prompt,
                user_input=user_input,
                parameters=version.parameters,
                timeout=timeout,
                tools=specs,
                history=history,
            )
        except Exception as error:
            if events is not None:
                events.append(
                    generation_event(version, user_input, history, started_at, error=str(error))
                )
            raise
        if events is not None:
            events.append(generation_event(version, user_input, history, started_at, completion))
        usage.update(completion.usage)
        if not completion.tool_calls:
            return ExecutionResult(
                text=completion.text,
                usage=dict(usage),
                sources=[source_payload(hit) for hit in hits],
                tool_calls=records,
                completions=round_number + 1,
            )
        if round_number == settings.MAX_TOOL_STEPS:
            raise ToolStepLimitExceeded(
                f"The agent kept calling tools after {settings.MAX_TOOL_STEPS} steps."
            )
        history.append(assistant_message(completion))
        for call in completion.tool_calls:
            record = timed_tool_call(call, tools, events)
            records.append(record)
            history.append(tool_message(call, record))
    raise ToolStepLimitExceeded("The tool loop ended without an answer.")
