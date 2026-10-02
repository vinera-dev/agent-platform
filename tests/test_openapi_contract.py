import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

SNAPSHOT = Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"
REGENERATE = "python manage.py spectacular --format openapi-json --file contracts/openapi-v1.json"


def current_schema():
    return APIClient().get("/v1/schema?format=json").json()


def operations(schema):
    return {
        (path, method): operation
        for path, item in schema["paths"].items()
        for method, operation in item.items()
    }


def test_api_matches_the_committed_contract():
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert current_schema() == committed, (
        f"The API no longer matches contracts/openapi-v1.json. "
        f"If the change is intentional and compatible, regenerate it with: {REGENERATE}"
    )


def test_no_committed_operation_disappears():
    committed = operations(json.loads(SNAPSHOT.read_text(encoding="utf-8")))
    current = operations(current_schema())

    assert set(committed) <= set(current)
