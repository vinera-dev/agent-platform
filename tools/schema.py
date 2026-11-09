import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

MAX_SCHEMA_BYTES = 16 * 1024
REFERENCE_KEYWORDS = ("$ref", "$dynamicRef")


class InvalidToolSchema(ValueError):
    pass


def find_external_references(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in REFERENCE_KEYWORDS and not (isinstance(value, str) and value.startswith("#")):
                found.append(str(value))
            else:
                found.extend(find_external_references(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(find_external_references(item))
    return found


def validate_input_schema(schema: Any) -> dict:
    if not isinstance(schema, dict):
        raise InvalidToolSchema("The input schema must be a JSON object.")
    if len(json.dumps(schema)) > MAX_SCHEMA_BYTES:
        raise InvalidToolSchema(f"The input schema must not exceed {MAX_SCHEMA_BYTES} bytes.")
    if schema.get("type") != "object":
        raise InvalidToolSchema('The input schema must declare "type": "object" at the top level.')
    if find_external_references(schema):
        raise InvalidToolSchema("Only local references to the same document are allowed.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise InvalidToolSchema(f"Not a valid JSON Schema: {error.message}") from error
    return schema
