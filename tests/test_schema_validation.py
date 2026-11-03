"""Our diagnostic formatting and offline schema resolution."""
import socket

import pytest

from generated_models.metadata import DllRelease, PluginInfo
from zero_infra_mod_registry.models.loading import serialize
from generated_models.loading import _VALIDATORS, validate_schema
from tests.fakes import mod_fixture


INFO = PluginInfo("Plugin", "Description", ["Author"], [])
DLL = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", "a" * 64, 1, INFO)


def test_schema_aggregates_nested_leaf_errors_with_release_identity() -> None:
    data = serialize(DLL)
    data["info"] = {**serialize(INFO), "authors": [False], "description": 42, "icon_url": 8}
    with pytest.raises(ValueError) as failure:
        validate_schema(data, "registry", "pluginRelease")
    for field in ["$.info.authors[0] (1.0.0)", "$.info.description (1.0.0)", "$.info.icon_url (1.0.0)"]:
        assert field in str(failure.value)


def test_bundled_schema_references_need_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(address: tuple[str, int], timeout: float | None = None,
                source_address: tuple[str, int] | None = None, *, all_errors: bool = False) -> socket.socket:
        raise AssertionError("Schema validation must not use the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    _VALIDATORS.clear()
    validate_schema(serialize(DLL), "registry", "pluginRelease")
    validate_schema(serialize(INFO), "plugin")
    validate_schema(serialize(mod_fixture()), "registry", "mod")
