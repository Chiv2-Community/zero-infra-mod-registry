"""Typed JSON boundary shared by the registry and gateway."""
from __future__ import annotations

import json
from typing import Dict, List, Never, Union, TypeAlias, cast

JsonValue: TypeAlias = Union[str, int, float, bool, None, List["JsonValue"], Dict[str, "JsonValue"]]
JsonObject: TypeAlias = Dict[str, JsonValue]


def _reject_constant(value: str) -> Never:
    raise ValueError(f"Invalid JSON constant: {value}")


def decode_json(text: str) -> JsonValue:
    # Reject Python's non-JSON constants, including in ignored/nested fields.
    # This is the sole cast at that external deserialization boundary.
    return cast(JsonValue, json.loads(text, parse_constant=_reject_constant))


def json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def json_array(value: JsonValue) -> List[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array")
    return value


def json_string(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a JSON string")
    return value


def optional_string(value: JsonValue) -> str | None:
    return None if value is None else json_string(value)


def json_bool(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Expected a JSON boolean")
    return value


def json_int(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Expected a JSON integer")
    return value


def string_array(value: JsonValue) -> List[str]:
    return [json_string(item) for item in json_array(value)]
