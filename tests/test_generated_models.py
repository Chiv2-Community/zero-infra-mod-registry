"""Generation drift, compatibility hooks, and runtime-check boundaries."""
from collections.abc import Callable
from pathlib import Path
import subprocess
import sys

import pytest

from generated_models.requests import Action, RegistrationRequest
from generated_models.json_types import JsonObject, JsonValue
from generated_models.metadata import Mod
from generated_models.loading import JsonCodec, dumps, loads, load as load_generated, serialize as serialize_generated
from generated_models.metadata import ModInfo, ModMarkerInfo, PluginInfo, PluginPackage
from zero_infra_mod_registry.models.loading import load, serialize
from tests.fakes import mod_fixture


def test_generated_sources_are_current() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "code_gen", "--check"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("loader", [load, load_generated])
def test_invalid_timestamp_keeps_release_context(loader: Callable[[JsonValue, type[Mod]], Mod]) -> None:
    data = serialize(mod_fixture().releases[0])
    data["release_date"] = "not a date"
    with pytest.raises(ValueError, match="release v1.0.0: release_date"):
        loader({"latest_release_info": serialize(mod_fixture().latest_release_info), "releases": [data]}, Mod)


def test_issue_request_structures_the_action_enum() -> None:
    request = load_generated({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0"}, RegistrationRequest)
    assert request.action is Action.ADD_DLL_RELEASE
    assert request.dll_file is None


def test_generated_compatibility_hooks_apply_to_nested_models() -> None:
    data = serialize(mod_fixture())
    restored = load_generated(data, Mod)
    assert serialize_generated(restored) == data
    dependency: JsonObject = {"repo_url": "https://github.com/Test/Pak", "version": "^1.0.0"}
    info = load_generated({"repo_url": "https://github.com/Test/Consumer", "name": "Consumer",
                           "description": "Description", "authors": ["Author"],
                           "mod_dependencies": [dependency], "dependencies": [dependency]}, ModInfo)
    assert len(info.mod_dependencies) == 1 and not info.dependencies
    assert serialize_generated(info)["dependencies"] == [dependency]
    marker = load_generated({"path": "/Marker", "hash": "hash", "associated_blueprints": None}, ModMarkerInfo)
    assert marker.associated_blueprints == []


def test_generated_wire_aliases_and_runtime_checks_are_separate() -> None:
    dependency: JsonObject = {"repo_url": "https://github.com/Test/Pak", "version": "^1.0.0"}
    data: JsonObject = {"name": "Plugin", "description": "Description", "authors": ["Author"],
            "$schema": "https://example.com/plugin.schema.json", "mod_dependencies": [dependency, dependency]}
    info = load_generated(data, PluginInfo)
    wire = serialize_generated(PluginPackage(info, []))
    assert wire["latest_release_info"] == {**data, "plugin_dependencies": [], "target": "shared"}
    with pytest.raises(ValueError, match="Duplicate plugin dependency"):
        load(data, PluginInfo)


def test_generated_json_text_api_round_trips_nested_models() -> None:
    model = mod_fixture()
    assert loads(dumps(model), Mod) == model
    assert serialize_generated(loads(dumps(model, indent=2), Mod)) == serialize_generated(model)
    with pytest.raises(ValueError, match="Invalid JSON constant: NaN"):
        loads('{"ignored": {"value": NaN}}', Mod)


def reverse_object_keys(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: reverse_object_keys(item) for key, item in reversed(value.items())}
    if isinstance(value, list):
        return [reverse_object_keys(item) for item in value]
    return value


@pytest.mark.parametrize("indent", [None, 2, 4])
def test_codec_text_key_order_is_independent_of_model_and_dictionary_order(indent: int | None) -> None:
    model = mod_fixture()
    data = serialize_generated(model)
    assert dumps(model, indent=indent) == dumps(data, indent=indent)
    assert dumps(data, indent=indent) == dumps(reverse_object_keys(data), indent=indent)


def test_codec_sorts_adapter_keys_and_preserves_array_order() -> None:
    codec = JsonCodec()

    def adapter(info: ModInfo) -> JsonObject:
        return {"z": [{"z": 1, "a": 2}, {"z": 3, "a": 4}], "a": info.name}

    codec.register_serializer(ModInfo, adapter)
    info = ModInfo("https://github.com/Test/Mod", "Consumer", "Description", ["Author"])
    assert codec.dumps(info) == '{"a": "Consumer", "z": [{"a": 2, "z": 1}, {"a": 4, "z": 3}]}'


def test_codec_keeps_json_and_schema_checks_at_the_boundary() -> None:
    codec = JsonCodec()
    checked: list[RegistrationRequest] = []
    codec.register_validator(RegistrationRequest, checked.append)
    with pytest.raises(ValueError, match=r"\$\.action"):
        codec.loads('{"action":"invalid","repo_url":"https://github.com/Test/Pak","release_tag":"v1.0.0"}', RegistrationRequest)
    assert not checked

    def non_json_adapter(info: ModInfo) -> JsonObject:
        return {"value": float("nan")}

    codec.register_serializer(ModInfo, non_json_adapter)
    with pytest.raises(ValueError, match="Out of range float"):
        codec.dumps(mod_fixture())


def test_codec_callbacks_apply_to_nested_models_after_first_use_and_are_isolated() -> None:
    codec = JsonCodec()
    package = PluginPackage(PluginInfo("Plugin", "Description", ["Author"]), [])
    wire = serialize_generated(package)
    # Prime both hook caches before adding consumer callbacks.
    codec.serialize(package)
    # An empty package is not schema-valid, so prime loading with a nested mod instead.
    mod = mod_fixture()
    codec.load(serialize_generated(mod), Mod)
    seen: list[ModInfo] = []
    codec.register_validator(ModInfo, seen.append)
    restored = codec.loads(codec.dumps(mod), Mod)
    assert seen == [restored.latest_release_info, *(release.info for release in restored.releases)]

    def reject_info(info: ModInfo) -> None:
        raise ValueError("consumer semantic check")

    codec.register_validator(ModInfo, reject_info)
    with pytest.raises(ValueError, match="consumer semantic check"):
        codec.load(serialize_generated(mod), Mod)
    assert load_generated(serialize_generated(mod), Mod) == mod

    def custom_info(info: PluginInfo) -> JsonObject:
        return {"consumer_name": info.name}

    codec.register_serializer(PluginInfo, custom_info)
    assert codec.serialize(package)["latest_release_info"] == {"consumer_name": "Plugin"}
    assert serialize_generated(package) == wire
