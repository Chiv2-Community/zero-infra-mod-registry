import socket

import pytest

from zero_infra_mod_registry.models.dll_metadata import PluginInfo, PluginTarget
from zero_infra_mod_registry.models.mod_metadata import ModInfo
from zero_infra_mod_registry.metadata_validation import metadata_validator as validator
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue


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


@pytest.mark.parametrize("target", list(PluginTarget))
def test_plugin_schema_accepts_target(target: PluginTarget) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"], "target": target.value}
    validator("plugin").validate(data)
    assert PluginInfo.from_dict(data).target is target


@pytest.mark.parametrize("target", [None, True, 1, [], {}, "", "Server", "both"])
def test_plugin_schema_rejects_invalid_target(target: JsonValue) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"], "target": target}
    assert not validator("plugin").is_valid(data)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
@pytest.mark.parametrize("repo", [".", "..", "../Pak", "Pak/Core", "Pak%2eCore", "Pak.Core?x=1", "Pak.Core#fragment"])
def test_schemas_reject_unsafe_pak_dependencies(kind: str, repo: str) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"],
                        "mod_dependencies": [{"repo_url": f"https://github.com/Test/{repo}", "version": "1.0.0"}]}
    assert not validator(kind).is_valid(data)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_schemas_keep_plugin_repository_names_strict(kind: str) -> None:
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"],
                        "plugin_dependencies": [{"repo_url": "https://github.com/Test/Plugin.Core", "version": "1.0.0"}]}
    assert not validator(kind).is_valid(data)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_shared_schema_references_resolve_without_network(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def block_connection(address: tuple[str, int], timeout: float | None = None,
                         source_address: tuple[str, int] | None = None, *, all_errors: bool = False) -> socket.socket:
        raise AssertionError("Bundled schemas must resolve without network access")

    monkeypatch.setattr(socket, "create_connection", block_connection)
    data: JsonObject = {"name": "Example", "description": "Description", "authors": ["Author"],
                        "mod_dependencies": [{"repo_url": "https://github.com/Test/Pak.Core", "version": "^1.0.0"}],
                        "plugin_dependencies": [{"repo_url": "https://github.com/Test/Plugin", "version": ">=1.0.0,<2.0.0"}]}
    validator(kind).validate(data)
