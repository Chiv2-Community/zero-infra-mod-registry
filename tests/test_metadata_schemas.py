from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from zero_infra_mod_registry.models.dll_metadata import PluginInfo
from zero_infra_mod_registry.models.mod_metadata import ModInfo
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, decode_json, json_object


SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def validator(kind: str) -> Draft202012Validator:
    schema = json_object(decode_json((SCHEMAS / f"{kind}.schema.json").read_text()))
    instance = Draft202012Validator(schema, format_checker=FormatChecker())
    instance.check_schema(schema)
    return instance


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_metadata_schemas_accept_dependency_fields(kind: str) -> None:
    data: JsonObject = {
        "$schema": f"https://example.com/{kind}.schema.json",
        "name": "Example", "description": "Description", "authors": ["Author"],
        "mod_dependencies": [{"repo_url": "https://github.com/Org/Mod", "version": "1.0.0"}],
        "plugin_dependencies": [{"repo_url": "https://github.com/Org/Plugin", "version": ">=1.0.0,<2.0.0"}],
        "icon_url": "https://example.com/icon.png", "image_urls": ["https://example.com/image.png"],
    }
    validator(kind).validate(data)
    if kind == "plugin":
        assert len(PluginInfo.from_dict(data).plugin_dependencies) == 1
    else:
        data["repo_url"] = "https://github.com/Org/Example"
        assert len(ModInfo.from_dict(data).plugin_dependencies) == 1


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_metadata_schemas_accept_minimal_metadata(kind: str) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"]}
    validator(kind).validate(data)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
@pytest.mark.parametrize("field,value", [
    ("name", None), ("authors", "Author"), ("mod_dependencies", None),
    ("plugin_dependencies", {}),
    ("plugin_dependencies", [{"repo_url": "https://github.com/Org/Plugin"}]),
    ("plugin_dependencies", [{"repo_url": "https://example.com/Org/Plugin", "version": "1.0.0"}]),
    ("plugin_dependencies", [{"repo_url": "https://github.com/Org/Plugin", "version": "latest"}]),
    ("plugin_dependencies", [{"repo_url": "https://github.com/Org/Plugin", "version": "^1.0.0,<2.0.0"}]),
])
def test_metadata_schemas_reject_invalid_structure(kind: str, field: str, value: JsonValue) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"], field: value}
    assert not validator(kind).is_valid(data)


@pytest.mark.parametrize("field,value", [
    ("name", "   "), ("authors", []), ("authors", [""]), ("unknown", True),
    ("icon_url", "http://example.com/icon.png"),
    ("image_urls", ["https://user:password@example.com/image.png"]),
])
def test_plugin_schema_rejects_invalid_metadata(field: str, value: JsonValue) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"], field: value}
    assert not validator("plugin").is_valid(data)


def test_legacy_dependencies_are_only_documented_for_mods() -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"],
                        "dependencies": [{"repo_url": "https://github.com/Org/Mod", "version": "^1.0.0"}]}
    assert validator("mod").is_valid(data)
    assert not validator("plugin").is_valid(data)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
@pytest.mark.parametrize("field", ["name", "description", "authors"])
def test_metadata_schemas_require_core_fields(kind: str, field: str) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"]}
    del data[field]
    assert not validator(kind).is_valid(data)
