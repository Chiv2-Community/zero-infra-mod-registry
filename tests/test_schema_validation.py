"""Schema diagnostics and stored-record compatibility."""
import socket

import pytest

from mod_registry_core.json_types import JsonValue
from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo
from zero_infra_mod_registry.models.mod_metadata import Mod
from zero_infra_mod_registry.utils.schema_validation import _VALIDATORS, validate_schema
from tests.fakes import mod_fixture


INFO = PluginInfo("Plugin", "Description", ["Author"], [])
DLL = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", "a" * 64, 1, INFO)


def test_schema_reports_all_fields_in_one_registration_error() -> None:
    with pytest.raises(ValueError) as failure:
        validate_schema({"name": "Plugin", "authors": [False], "target": "both", "typo": True}, "plugin")
    message = str(failure.value)
    for detail in ["description", "$.authors[0]", "$.target", "typo"]:
        assert detail in message


def test_plugin_info_reports_nested_fields() -> None:
    data = DLL.package_dict()
    data["info"] = {**INFO.asdict(), "authors": [False], "description": 42}
    with pytest.raises(ValueError) as failure:
        validate_schema(data, "registry", "pluginRelease")
    for field in ["$.info.authors[0]", "$.info.description"]:
        assert field in str(failure.value)


def test_package_diagnostics_include_release_tag() -> None:
    data = DLL.package_dict()
    data["size"] = False
    with pytest.raises(ValueError) as failure:
        validate_schema(data, "registry", "pluginRelease")
    assert "$.size (1.0.0)" in str(failure.value)


def test_nullable_stored_metadata_remains_readable() -> None:
    data = DLL.package_dict()
    data["info"] = {**INFO.asdict(), "repo_url": None, "$schema": "legacy-schema-name"}
    assert DllRelease.from_package_dict("Test", "Plugin", data).info == INFO


def test_stored_mod_keeps_legacy_dependencies_extra_fields_and_naive_dates() -> None:
    data = mod_fixture().asdict()
    data["unknown_legacy_field"] = True
    mod = Mod.from_dict(data)
    assert mod == mod_fixture()


@pytest.mark.parametrize("field,value", [("silent_load", "true"), ("path", False)])
def test_stored_manifest_schema_identifies_asset_fields(field: str, value: JsonValue) -> None:
    data = mod_fixture().releases[0].asdict()
    data["manifest"] = {"blueprints": [{"path": "/Game/Test", "hash": "abc", field: value}]}
    with pytest.raises(ValueError) as failure:
        validate_schema(data, "registry", "modRelease")
    assert f"$.manifest.blueprints[0].{field}" in str(failure.value)


def test_bundled_schema_references_need_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(address: tuple[str, int], timeout: float | None = None,
                source_address: tuple[str, int] | None = None, *, all_errors: bool = False) -> socket.socket:
        raise AssertionError("Schema validation must not use the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    _VALIDATORS.clear()
    validate_schema(DLL.package_dict(), "registry", "pluginRelease")
    validate_schema(INFO.asdict(), "plugin")
    validate_schema(mod_fixture().asdict(), "registry", "mod")
