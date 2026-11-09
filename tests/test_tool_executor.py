import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from tools.executor import (
    DomainNotAllowed,
    InvalidToolArguments,
    ToolCallFailed,
    ToolDisabled,
    execute_tool,
    host_allowed,
)
from tools.models import Tool

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "properties": {"date": {"type": "string"}, "size": {"type": "integer"}},
    "required": ["date"],
    "additionalProperties": False,
}


class Recorder:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        return self.handler(request)

    @property
    def transport(self):
        return httpx.MockTransport(self)


def ok(request):
    return httpx.Response(200, json={"slots": ["09:00", "10:30"]})


@pytest.fixture
def make_tool(tenant):
    def factory(url="https://scheduler.example.com/slots", **extra):
        fields = {
            "tenant": tenant,
            "name": "lookup_slots",
            "description": "Find slots.",
            "input_schema": SCHEMA,
            "endpoint_url": url,
        }
        return Tool.objects.create(**{**fields, **extra})

    return factory


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("example.com", True),
        ("api.example.com", True),
        ("API.Example.COM.", True),
        ("deep.api.example.com", True),
        ("evilexample.com", False),
        ("example.com.evil.net", False),
        ("example.org", False),
        ("127.0.0.1", False),
    ],
)
def test_host_allow_list_matches_exact_hosts_and_subdomains_only(host, expected):
    assert host_allowed(host, ["example.com"]) is expected


def test_empty_allow_list_blocks_everything():
    assert host_allowed("example.com", []) is False
    assert host_allowed("example.com", [""]) is False


def test_calls_the_endpoint_and_returns_the_parsed_body(make_tool):
    recorder = Recorder(ok)

    result = execute_tool(make_tool(), {"date": "2026-01-05"}, transport=recorder.transport)

    assert result == {"slots": ["09:00", "10:30"]}
    sent = recorder.requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == "https://scheduler.example.com/slots"
    assert json.loads(sent.content) == {"arguments": {"date": "2026-01-05"}}
    assert sent.headers["content-type"] == "application/json"


def test_domain_outside_the_allow_list_is_blocked_before_any_request(make_tool):
    recorder = Recorder(ok)
    tool = make_tool(url="https://evil.example.net/steal")

    with pytest.raises(DomainNotAllowed, match="evil.example.net"):
        execute_tool(tool, {"date": "2026-01-05"}, transport=recorder.transport)

    assert recorder.requests == []


def test_removing_a_domain_from_the_allow_list_blocks_existing_tools(make_tool, settings):
    tool = make_tool()
    settings.TOOL_ALLOWED_DOMAINS = []
    recorder = Recorder(ok)

    with pytest.raises(DomainNotAllowed):
        execute_tool(tool, {"date": "2026-01-05"}, transport=recorder.transport)

    assert recorder.requests == []


def test_invalid_arguments_never_reach_the_endpoint(make_tool):
    recorder = Recorder(ok)
    tool = make_tool()

    for arguments in ({}, {"date": 5}, {"date": "x", "extra": 1}, "text", ["date"]):
        with pytest.raises(InvalidToolArguments):
            execute_tool(tool, arguments, transport=recorder.transport)

    assert recorder.requests == []


def test_argument_errors_are_described(make_tool):
    with pytest.raises(InvalidToolArguments, match="size: 'many' is not of type 'integer'"):
        execute_tool(make_tool(), {"date": "x", "size": "many"})


def test_disabled_tools_are_not_called(make_tool):
    recorder = Recorder(ok)

    with pytest.raises(ToolDisabled):
        execute_tool(make_tool(is_active=False), {"date": "x"}, transport=recorder.transport)

    assert recorder.requests == []


def test_redirects_are_not_followed(make_tool):
    recorder = Recorder(
        lambda request: httpx.Response(302, headers={"location": "https://evil.example.net/"})
    )

    with pytest.raises(ToolCallFailed, match="redirect"):
        execute_tool(make_tool(), {"date": "x"}, transport=recorder.transport)

    assert len(recorder.requests) == 1


def test_error_statuses_fail_the_call(make_tool):
    recorder = Recorder(lambda request: httpx.Response(503))

    with pytest.raises(ToolCallFailed, match="503"):
        execute_tool(make_tool(), {"date": "x"}, transport=recorder.transport)


def test_timeouts_fail_the_call(make_tool):
    def slow(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ToolCallFailed, match="timed out"):
        execute_tool(make_tool(), {"date": "x"}, transport=Recorder(slow).transport)


def test_connection_errors_fail_the_call(make_tool):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ToolCallFailed, match="ConnectError"):
        execute_tool(make_tool(), {"date": "x"}, transport=Recorder(refuse).transport)


def test_oversized_responses_are_cut_off(make_tool, settings):
    settings.TOOL_MAX_RESPONSE_BYTES = 100
    recorder = Recorder(lambda request: httpx.Response(200, content=b"x" * 500))

    with pytest.raises(ToolCallFailed, match="exceeded 100 bytes"):
        execute_tool(make_tool(), {"date": "x"}, transport=recorder.transport)


def test_plain_text_bodies_are_returned_as_text(make_tool):
    recorder = Recorder(lambda request: httpx.Response(200, text="three slots left"))

    assert execute_tool(make_tool(), {"date": "x"}, transport=recorder.transport) == (
        "three slots left"
    )


class EchoHandler(BaseHTTPRequestHandler):
    delay = 0.0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        received = json.loads(self.rfile.read(length))
        time.sleep(self.delay)
        payload = json.dumps({"echo": received["arguments"]}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            return

    def log_message(self, format, *args):
        return


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/tool"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_real_http_round_trip(make_tool, local_server, settings):
    settings.TOOL_ALLOWED_DOMAINS = ["127.0.0.1"]

    result = execute_tool(make_tool(url=local_server), {"date": "2026-01-05"})

    assert result == {"echo": {"date": "2026-01-05"}}


def test_real_http_timeout(make_tool, local_server, settings):
    settings.TOOL_ALLOWED_DOMAINS = ["127.0.0.1"]
    settings.TOOL_TIMEOUT_SECONDS = 0.2
    EchoHandler.delay = 1.0
    try:
        with pytest.raises(ToolCallFailed, match="timed out"):
            execute_tool(make_tool(url=local_server), {"date": "x"})
    finally:
        EchoHandler.delay = 0.0


def test_real_http_is_blocked_when_the_host_is_not_allowed(make_tool, local_server):
    with pytest.raises(DomainNotAllowed):
        execute_tool(make_tool(url=local_server), {"date": "x"})
