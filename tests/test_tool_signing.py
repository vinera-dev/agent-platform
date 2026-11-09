import json

import httpx
import pytest

from tools.executor import ToolCallFailed, execute_tool
from tools.models import Tool
from tools.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign, signed_headers, verify

SECRET = "whsec_test"
BODY = b'{"arguments":{"date":"2026-01-05"}}'
KNOWN_SIGNATURE = "sha256=72fcb232d04d329d93a5c28eb5c72a6f83d9492cb55d7bae533d4aa4d9c51fa8"
NOW = 1_700_000_000


def test_signature_matches_a_known_vector():
    assert sign(SECRET, NOW, BODY) == KNOWN_SIGNATURE


def test_a_valid_signature_verifies():
    headers = signed_headers(SECRET, BODY, now=NOW)

    assert headers[SIGNATURE_HEADER] == KNOWN_SIGNATURE
    assert verify(SECRET, headers[TIMESTAMP_HEADER], headers[SIGNATURE_HEADER], BODY, now=NOW)


def test_a_tampered_body_fails_verification():
    headers = signed_headers(SECRET, BODY, now=NOW)

    assert not verify(
        SECRET,
        headers[TIMESTAMP_HEADER],
        headers[SIGNATURE_HEADER],
        BODY.replace(b"2026", b"2027"),
        now=NOW,
    )


def test_a_wrong_secret_fails_verification():
    headers = signed_headers(SECRET, BODY, now=NOW)

    assert not verify("other", headers[TIMESTAMP_HEADER], headers[SIGNATURE_HEADER], BODY, now=NOW)


def test_a_replayed_old_request_is_rejected():
    headers = signed_headers(SECRET, BODY, now=NOW)

    assert verify(SECRET, headers[TIMESTAMP_HEADER], headers[SIGNATURE_HEADER], BODY, now=NOW + 299)
    assert not verify(
        SECRET, headers[TIMESTAMP_HEADER], headers[SIGNATURE_HEADER], BODY, now=NOW + 301
    )
    assert not verify(
        SECRET, headers[TIMESTAMP_HEADER], headers[SIGNATURE_HEADER], BODY, now=NOW - 301
    )


def test_a_changed_timestamp_invalidates_the_signature():
    headers = signed_headers(SECRET, BODY, now=NOW)

    assert not verify(SECRET, str(NOW + 1), headers[SIGNATURE_HEADER], BODY, now=NOW)


@pytest.mark.parametrize(
    ("timestamp", "signature"),
    [
        (None, KNOWN_SIGNATURE),
        (str(NOW), None),
        ("", ""),
        ("soon", KNOWN_SIGNATURE),
        (str(NOW), "x"),
    ],
)
def test_missing_or_malformed_headers_fail(timestamp, signature):
    assert not verify(SECRET, timestamp, signature, BODY, now=NOW)


def test_signature_without_the_prefix_fails():
    bare = KNOWN_SIGNATURE.removeprefix("sha256=")

    assert not verify(SECRET, str(NOW), bare, BODY, now=NOW)


@pytest.mark.django_db
class TestExecutorSigning:
    @pytest.fixture
    def tool(self, tenant):
        return Tool.objects.create(
            tenant=tenant,
            name="lookup_slots",
            description="Find slots.",
            input_schema={"type": "object"},
            endpoint_url="https://scheduler.example.com/slots",
        )

    def receiver(self, secret):
        def handler(request):
            valid = verify(
                secret,
                request.headers.get(TIMESTAMP_HEADER),
                request.headers.get(SIGNATURE_HEADER),
                request.content,
            )
            return httpx.Response(200 if valid else 401, json={"signed": valid})

        return httpx.MockTransport(handler)

    def test_outgoing_calls_carry_a_signature_the_receiver_can_verify(self, tool):
        result = execute_tool(tool, {"date": "x"}, transport=self.receiver(tool.signing_secret))

        assert result == {"signed": True}

    def test_a_receiver_with_a_different_secret_rejects_the_call(self, tool):
        with pytest.raises(ToolCallFailed, match="401"):
            execute_tool(tool, {"date": "x"}, transport=self.receiver("not-the-secret"))

    def test_each_tool_gets_its_own_random_secret(self, tool, tenant):
        other = Tool.objects.create(
            tenant=tenant,
            name="other_tool",
            description="d",
            input_schema={"type": "object"},
            endpoint_url="https://scheduler.example.com/other",
        )

        assert len(tool.signing_secret) == 64
        assert tool.signing_secret != other.signing_secret

    def test_the_secret_is_revealed_only_when_the_tool_is_created(
        self, tenant, issued_key, client_for
    ):
        client = client_for(issued_key.raw_key)
        body = {
            "name": "lookup_slots",
            "description": "d",
            "input_schema": {"type": "object"},
            "endpoint_url": "https://scheduler.example.com/slots",
        }

        created = client.post("/v1/tools", body, format="json").json()
        listed = client.get("/v1/tools").json()[0]
        fetched = client.get(f"/v1/tools/{created['id']}").json()

        assert Tool.objects.get(pk=created["id"]).signing_secret == created["signing_secret"]
        assert "signing_secret" not in listed
        assert "signing_secret" not in fetched
        assert created["signing_secret"] not in json.dumps([listed, fetched])
