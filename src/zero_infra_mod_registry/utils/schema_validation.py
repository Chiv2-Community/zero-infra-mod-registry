"""Validate JSON boundaries with bundled, offline schemas."""
from pathlib import Path
from collections.abc import Iterator

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator

from mod_registry_core.json_types import JsonObject, JsonValue, decode_json, json_object, json_string


_VALIDATORS: dict[tuple[str, str | None], Validator] = {}


def schema_validator(kind: str, definition: str | None = None) -> Validator:
    if kind not in {"mod", "plugin", "registry"}:
        raise ValueError("Unknown metadata schema")
    key = kind, definition
    if key in _VALIDATORS:
        return _VALIDATORS[key]
    schemas = Path(__file__).resolve().parents[1] / "schemas"
    if not schemas.exists():
        schemas = Path(__file__).resolve().parents[3] / "schemas"
    documents: JsonObject = {}
    for name in ("common", "mod", "plugin", "registry"):
        document = json_object(decode_json((schemas / f"{name}.schema.json").read_text()))
        documents[name] = document
    reference = json_string(json_object(documents[kind])["$id"])
    if definition is not None:
        reference += f"#/$defs/{definition}"
    # Embedded $id resources resolve references without remote retrieval.
    schema: JsonObject = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": reference, "$defs": documents}
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.check_schema(schema)
    _VALIDATORS[key] = validator
    return validator


def _release_label(value: JsonValue) -> str:
    if isinstance(value, dict):
        if "organization" in value:
            return f" ({value.get('organization', '?')}/{value.get('name', '?')} {value.get('version', '?')})"
        if isinstance(value.get("tag"), str):
            return f" ({value['tag']})"
    return ""


def _diagnostic(error: ValidationError, value: JsonValue) -> str:
    release = _release_label(value)
    # Keep release identity beside the schema's precise JSON path.
    for part in error.absolute_path:
        if isinstance(value, dict):
            value = value.get(str(part))
        elif isinstance(value, list) and isinstance(part, int):
            value = value[part]
        else:
            break
        release = _release_label(value) or release
    return f"{error.json_path}{release}: {error.message}"


def _leaf_errors(error: ValidationError) -> Iterator[ValidationError]:
    if error.context:
        for child in error.context:
            yield from _leaf_errors(child)
    else:
        yield error


def validate_schema(value: JsonValue, kind: str, definition: str | None = None) -> None:
    validator = schema_validator(kind, definition)
    errors = sorted({_diagnostic(leaf, value) for error in validator.iter_errors(value) for leaf in _leaf_errors(error)})
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(f"- {error}" for error in errors))
