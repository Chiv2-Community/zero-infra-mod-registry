"""Schema generation, compatibility normalization, and public contracts."""
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import pytest

from mod_registry_core.generated_requests import Action, RegistrationRequest
from mod_registry_core.json_types import JsonObject
from mod_registry_core.registration import load_registration_request
from zero_infra_mod_registry.models import Dependency, Mod, ModInfo
from zero_infra_mod_registry.models.dll_metadata import PluginInfo
from zero_infra_mod_registry.models.pak_manifest import Manifest, PakInventory
from zero_infra_mod_registry.utils.schema_validation import validate_schema
from tests.fakes import mod_fixture


def test_generated_sources_are_current() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "scripts/generate_models.py", "--check"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("model", [Mod, ModInfo, PluginInfo, Manifest, PakInventory, RegistrationRequest])
def test_public_models_are_generated(model: type[Mod | ModInfo | PluginInfo | Manifest | PakInventory | RegistrationRequest]) -> None:
    assert is_dataclass(model)
    assert ".generated" in model.__module__


def test_both_dependency_fields_are_generated_fields() -> None:
    dependencies = [Dependency("https://github.com/Test/Dep", "1.0.0")]
    info = ModInfo(repo_url="https://github.com/Test/Pak", name="Pak", description="Description", authors=["Author"],
                   dependencies=dependencies, mod_dependencies=dependencies)
    assert info.dependencies == info.mod_dependencies == dependencies


@pytest.mark.parametrize("kind", ["mod", "mod-metadata"])
@pytest.mark.parametrize("spelling", ["dependencies", "mod_dependencies", "both", "neither"])
def test_dependency_alias_is_conditionally_required(kind: str, spelling: str) -> None:
    data: JsonObject = {"repo_url": "https://github.com/Test/Pak", "name": "Pak", "description": "Description", "authors": ["Author"]}
    if spelling in {"dependencies", "both"}:
        data["dependencies"] = []
    if spelling in {"mod_dependencies", "both"}:
        data["mod_dependencies"] = []
    if spelling == "neither":
        with pytest.raises(ValueError, match="mod_dependencies"):
            validate_schema(data, kind)
    else:
        validate_schema(data, kind)


def test_dependency_normalization_is_external_and_deduplicates() -> None:
    data: JsonObject = {"repo_url": "https://github.com/Test/Pak", "name": "Pak", "description": "Description", "authors": ["Author"],
                        "dependencies": [{"repo_url": "https://github.com/Test/Dep", "version": "^1.0.0"}],
                        "mod_dependencies": [{"repo_url": "https://github.com/test/dep", "version": "^1.0.0"},
                                             {"repo_url": "https://github.com/Test/Other", "version": "2.0.0"}]}
    info = ModInfo.from_dict(data)
    assert len(info.mod_dependencies) == 2
    assert info.dependencies == []  # Deprecated input has been consumed.
    assert info.asdict()["dependencies"] == info.asdict()["mod_dependencies"]
    assert ModInfo.from_dict(info.asdict()) == info


@pytest.mark.parametrize("field", ["dependencies", "mod_dependencies"])
def test_normalization_does_not_hide_invalid_alias(field: str) -> None:
    data = mod_fixture().latest_release_info.asdict()
    data[field] = None
    with pytest.raises(ValueError, match=field):
        ModInfo.from_dict(data)


def test_naive_iso_timestamps_remain_supported() -> None:
    mod = mod_fixture(date=datetime(2023, 1, 1, 12, 30))
    assert Mod.from_dict(mod.asdict()) == mod


def test_invalid_timestamp_keeps_release_context() -> None:
    data = mod_fixture().releases[0].asdict()
    data["release_date"] = "not a date"
    with pytest.raises(ValueError, match="release v1.0.0: release_date"):
        Mod.from_dict({"latest_release_info": mod_fixture().latest_release_info.asdict(), "releases": [data]})


def test_issue_request_uses_generated_model_and_schema() -> None:
    request = load_registration_request({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0"})
    assert isinstance(request, RegistrationRequest)
    assert request.action is Action.ADD_DLL_RELEASE
    assert request.dll_file is None
    with pytest.raises(ValueError, match="dll_file"):
        load_registration_request({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0", "dll_file": None})
