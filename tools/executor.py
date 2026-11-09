import json
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from jsonschema import Draft202012Validator

from tools.models import Tool
from tools.signing import signed_headers


class ToolExecutionError(Exception):
    pass


class ToolDisabled(ToolExecutionError):
    pass


class DomainNotAllowed(ToolExecutionError):
    pass


class InvalidToolArguments(ToolExecutionError):
    pass


class ToolCallFailed(ToolExecutionError):
    pass


def normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def host_allowed(host: str, allowed_domains: list[str]) -> bool:
    host = normalize_host(host)
    for domain in allowed_domains:
        domain = normalize_host(domain)
        if domain and (host == domain or host.endswith(f".{domain}")):
            return True
    return False


def url_allowed(url: str) -> bool:
    host = urlsplit(url).hostname
    return bool(host) and host_allowed(host, settings.TOOL_ALLOWED_DOMAINS)


def validate_arguments(tool: Tool, arguments: Any) -> dict:
    if not isinstance(arguments, dict):
        raise InvalidToolArguments("Tool arguments must be a JSON object.")
    errors = sorted(
        Draft202012Validator(tool.input_schema).iter_errors(arguments),
        key=lambda error: list(error.path),
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or 'arguments'}: {error.message}"
            for error in errors[:5]
        )
        raise InvalidToolArguments(f"Invalid arguments for {tool.name}: {details}")
    return arguments


def read_limited(response: httpx.Response, limit: int) -> bytes:
    received = bytearray()
    for part in response.iter_bytes():
        received.extend(part)
        if len(received) > limit:
            raise ToolCallFailed(f"The tool response exceeded {limit} bytes.")
    return bytes(received)


def parse_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def execute_tool(
    tool: Tool, arguments: Any, *, transport: httpx.BaseTransport | None = None
) -> Any:
    if not tool.is_active:
        raise ToolDisabled(f"The tool {tool.name} is disabled.")
    arguments = validate_arguments(tool, arguments)
    if not url_allowed(tool.endpoint_url):
        host = urlsplit(tool.endpoint_url).hostname
        raise DomainNotAllowed(f"The domain {host} is not in the allow-list.")
    body = json.dumps({"arguments": arguments}, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json", **signed_headers(tool.signing_secret, body)}
    try:
        client = httpx.Client(
            timeout=settings.TOOL_TIMEOUT_SECONDS, follow_redirects=False, transport=transport
        )
        with (
            client,
            client.stream("POST", tool.endpoint_url, content=body, headers=headers) as reply,
        ):
            if reply.is_redirect:
                raise ToolCallFailed("The tool endpoint answered with a redirect.")
            if reply.status_code >= 400:
                raise ToolCallFailed(f"The tool endpoint answered with {reply.status_code}.")
            raw = read_limited(reply, settings.TOOL_MAX_RESPONSE_BYTES)
    except httpx.TimeoutException as error:
        raise ToolCallFailed("The tool call timed out.") from error
    except httpx.HTTPError as error:
        raise ToolCallFailed(f"The tool call failed: {error.__class__.__name__}.") from error
    return parse_body(raw)
