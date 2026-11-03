"""Generation drift, compatibility hooks, and runtime-check boundaries."""
from pathlib import Path
import subprocess
import sys

import pytest

from generated_models.requests import Action
from mod_registry_core.registration import load_registration_request
from mod_registry_core.json_types import JsonObject
from generated_models.metadata import Mod
from generated_models.loading import load as load_generated, serialize as serialize_generated
from generated_models.metadata import ModInfo, ModMarkerInfo, PluginInfo, PluginPackage
from zero_infra_mod_registry.models.loading import load, serialize
from tests.fakes import mod_fixture


def test_generated_sources_are_current() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "code_gen", "--check"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_timestamp_keeps_release_context() -> None:
    data = serialize(mod_fixture().releases[0])
    data["release_date"] = "not a date"
    with pytest.raises(ValueError, match="release v1.0.0: release_date"):
        load({"latest_release_info": serialize(mod_fixture().latest_release_info), "releases": [data]}, Mod)


def test_issue_request_structures_the_action_enum() -> None:
    request = load_registration_request({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0"})
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
