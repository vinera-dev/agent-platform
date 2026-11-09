import hashlib
import json
import re
from uuid import UUID

from rest_framework.exceptions import ValidationError

HEADER = "Idempotency-Key"
KEY_PATTERN = re.compile(r"^[\x21-\x7e]{1,128}$")


def read_idempotency_key(request) -> str:
    key = request.headers.get(HEADER)
    if key is None:
        return ""
    if not KEY_PATTERN.match(key):
        raise ValidationError(
            {HEADER: "Must be 1 to 128 printable ASCII characters without spaces."}
        )
    return key


def request_fingerprint(agent_id: UUID, payload: dict) -> str:
    canonical = json.dumps(
        {"agent": str(agent_id), "input": payload}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
