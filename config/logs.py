import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

CONTEXT_FIELDS = ("tenant_id", "run_id")

_log_context: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)


def current_context() -> dict[str, str]:
    return _log_context.get() or {}


STANDARD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


@contextmanager
def bind_log_context(**fields: Any) -> Iterator[None]:
    values = {key: str(value) for key, value in fields.items() if value is not None}
    token = _log_context.set({**current_context(), **values})
    try:
        yield
    finally:
        _log_context.reset(token)


def install_log_context() -> None:
    current = logging.getLogRecordFactory()
    if getattr(current, "carries_log_context", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        for key, value in current_context().items():
            setattr(record, key, value)
        return record

    factory.carries_log_context = True
    logging.setLogRecordFactory(factory)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in STANDARD_ATTRIBUTES and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)
