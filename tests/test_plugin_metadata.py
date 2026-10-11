from dataclasses import replace
import json
from pathlib import Path

import pytest
import requests

from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo, dependency_matches, validate_dll_entries
from zero_infra_mod_registry.models.mod_metadata import Dependency, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue
from tests.fakes import FakeGithub, FakeRetriever, response_fixture

INFO = PluginInfo("Display name", "Description", ["Author"], [])
ENTRY = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", "a" * 64, 1, INFO)


def test_plugin_json_is_fetched_from_exact_release_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert timeout == 60
        return response_fixture(json.dumps(INFO.asdict()).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    result = GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), "v1.0.0-RC2")
    assert result == INFO
    assert calls == ["https://raw.githubusercontent.com/Test/Plugin/v1.0.0-RC2/plugin.json"]


@pytest.mark.parametrize("status,body", [(404, b"missing"), (500, b"error"), (200, b"invalid JSON"), (200, b"{}")])
def test_missing_or_invalid_plugin_json_is_rejected(monkeypatch: pytest.MonkeyPatch, status: int, body: bytes) -> None:
    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(body, url, status)
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises((ValueError, requests.HTTPError)):
        GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), "v1.0.0")


@pytest.mark.parametrize("field,value", [("name", ""), ("description", None), ("authors", "Author"),
                                         ("authors", []), ("authors", [False]), ("dependencies", {}),
                                         ("dependencies", [{"repo_url": "https://evil.com/a/b", "version": "1.0.0"}]),
                                         ("dependencies", [{"repo_url": "https://github.com/Test/Other", "version": "latest"}])])
def test_plugin_info_rejects_invalid_fields(field: str, value: JsonValue) -> None:
    data: JsonObject = {**INFO.asdict(), field: value}
    with pytest.raises(ValueError):
        PluginInfo.from_dict(data)


def test_metadata_round_trip_and_legacy_compatibility() -> None:
    assert DllRelease.from_dict(ENTRY.asdict()) == ENTRY
    legacy = replace(ENTRY, info=None)
    assert DllRelease.from_dict(legacy.asdict()) == legacy
    assert "info" not in legacy.asdict()


def test_registry_requires_registered_dependency_versions() -> None:
    info = replace(INFO, dependencies=[Dependency("https://github.com/Test/Other", ">=1.0.0,<2.0.0")])
    plugin = replace(ENTRY, info=info)
    dependency = replace(ENTRY, name="Other", info=None)
    assert validate_dll_entries([plugin.asdict(), dependency.asdict()]) == [plugin, dependency]
    with pytest.raises(ValueError, match="Unregistered plugin dependency"):
        validate_dll_entries([plugin.asdict()])
    with pytest.raises(ValueError, match="Unregistered plugin dependency"):
        validate_dll_entries([plugin.asdict(), replace(dependency, version="2.0.0").asdict()])


@pytest.mark.parametrize("version,requirement,expected", [("1.2.0", "^1.0.0", True), ("2.0.0", "^1.0.0", False),
                                                         ("0.2.5", "^0.2.0", True), ("0.3.0", "^0.2.0", False),
                                                         ("1.0.0-RC2", ">=1.0.0", False)])
def test_dependency_version_matching(version: str, requirement: str, expected: bool) -> None:
    assert dependency_matches(version, requirement) == expected


def test_new_registration_requires_info_and_does_not_write_on_failure(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    retriever.dll = replace(ENTRY, info=None)
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.dll_index_path).exists()
    retriever.dll = replace(ENTRY, info=replace(INFO, dependencies=[Dependency("https://github.com/Test/Missing", "1.0.0")]))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0", dry_run=True)
    assert not Path(registry.dll_index_path).exists()
