from dataclasses import replace
import json
from pathlib import Path

import pytest
import requests

from zero_infra_mod_registry.models.dll_metadata import DllRelease, Plugin, PluginInfo, PluginTarget, dependency_matches, validate_dll_entries
from zero_infra_mod_registry.models.mod_metadata import Dependency, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from mod_registry_core.json_types import JsonObject, JsonValue, decode_json, json_object
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, FakeRetriever, response_fixture

INFO = PluginInfo("Display name", "Description", ["Author"], [])
ENTRY = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", "a" * 64, 1, INFO)


def test_plugin_json_is_fetched_from_exact_release_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert timeout == 60
        return response_fixture(json.dumps(INFO.asdict()).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    result = GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), FakeRelease(tag_name="v1.0.0-RC2").as_release())
    assert result == replace(INFO, repo_url="https://github.com/Test/Plugin")
    assert calls == ["https://raw.githubusercontent.com/Test/Plugin/v1.0.0-RC2/plugin.json"]


@pytest.mark.parametrize("status,body", [(404, b"missing"), (500, b"error"), (200, b"invalid JSON"), (200, b"{}")])
def test_missing_or_invalid_plugin_json_is_rejected(monkeypatch: pytest.MonkeyPatch, status: int, body: bytes) -> None:
    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(body, url, status)
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises((ValueError, requests.HTTPError)):
        GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), FakeRelease().as_release())


@pytest.mark.parametrize("field,value", [("name", ""), ("description", None), ("authors", "Author"),
                                         ("authors", []), ("authors", [False]), ("plugin_dependencies", {}),
                                         ("plugin_dependencies", [{"repo_url": "https://evil.com/a/b", "version": "1.0.0"}]),
                                         ("plugin_dependencies", [{"repo_url": "https://github.com/Test/Other", "version": "latest"}])])
def test_plugin_info_rejects_invalid_fields(field: str, value: JsonValue) -> None:
    data: JsonObject = {**INFO.asdict(), field: value}
    with pytest.raises(ValueError):
        PluginInfo.from_dict(data)


def test_metadata_round_trip_and_legacy_compatibility() -> None:
    assert DllRelease.from_dict(ENTRY.asdict()) == ENTRY
    legacy = replace(ENTRY, info=None)
    assert DllRelease.from_dict(legacy.asdict()) == legacy
    assert "info" not in legacy.asdict()


@pytest.mark.parametrize("target", list(PluginTarget))
def test_plugin_target_round_trips(target: PluginTarget) -> None:
    info = PluginInfo.from_dict({**INFO.asdict(), "target": target.value})
    assert info.target is target
    assert info.asdict()["target"] == target.value
    release = replace(ENTRY, info=info, tag="v1.0.0")
    assert DllRelease.from_dict(release.asdict()) == release
    assert DllRelease.from_package_dict("Test", "Plugin", release.package_dict()) == release
    assert Plugin.from_dict("Test", "Plugin", Plugin([release]).asdict()).releases == [release]


def test_legacy_plugin_metadata_without_target_defaults_to_shared() -> None:
    data = INFO.asdict()
    del data["target"]
    assert PluginInfo.from_dict(data).target is PluginTarget.SHARED
    package = Plugin([ENTRY]).asdict()
    latest = json_object(package["latest_release_info"])
    del latest["target"]
    package["latest_release_info"] = latest
    release = ENTRY.package_dict()
    release["info"] = data
    package["releases"] = [release]
    assert Plugin.from_dict("Test", "Plugin", package).releases == [replace(ENTRY, tag="1.0.0")]


@pytest.mark.parametrize("target", [None, True, 1, [], {}, "", "Server", "both", "server,client"])
def test_invalid_plugin_target_is_rejected(target: JsonValue) -> None:
    with pytest.raises(ValueError):
        PluginInfo.from_dict({**INFO.asdict(), "target": target})


@pytest.mark.parametrize("target", [None, *list(PluginTarget)])
@pytest.mark.parametrize("uploaded", [False, True])
def test_retrieval_and_registration_preserve_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: PluginTarget | None, uploaded: bool,
) -> None:
    binary = b"DLL bytes"
    data = INFO.asdict()
    if target is None:
        del data["target"]
    else:
        data["target"] = target.value
    metadata_url = "https://example.com/plugin.json" if uploaded else "https://raw.githubusercontent.com/Test/Plugin/v1.0.0/plugin.json"
    calls: list[str] = []

    def get(url: str, *, timeout: int, stream: bool = False) -> requests.Response:
        assert timeout == 60
        calls.append(url)
        if url == metadata_url:
            assert not stream
            return response_fixture(json.dumps(data).encode(), url)
        assert url == ENTRY.download_url and stream
        return response_fixture(binary, url)

    monkeypatch.setattr(requests, "get", get)
    assets = [FakeAsset(size=len(binary))]
    if uploaded:
        assets.append(FakeAsset(name="plugin.json", browser_download_url=metadata_url))
    client = FakeGithub([FakeRelease(assets=assets)])
    retriever = GithubModMetadataRetriever(client.as_github())
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    package = json_object(decode_json((Path(registry.plugin_packages_dir) / "Test/Plugin.json").read_text()))
    expected = target or PluginTarget.SHARED
    assert json_object(package["latest_release_info"])["target"] == expected.value
    restored = Plugin.from_dict("Test", "Plugin", package)
    assert restored.releases[0].info is not None
    assert restored.releases[0].info.target is expected
    assert "manifest" not in restored.releases[0].package_dict()
    assert registry.validate_dll_db(verify_downloads=True)
    assert calls == [metadata_url, ENTRY.download_url, ENTRY.download_url]


@pytest.mark.parametrize("repo", [".", "..", "../Pak", "Pak/Core", "Pak%2eCore", "Pak.Core?x=1", "Pak.Core#fragment"])
def test_pak_dependency_paths_remain_strict(repo: str) -> None:
    with pytest.raises(ValueError, match="GitHub repository"):
        PluginInfo.from_dict({**INFO.asdict(), "mod_dependencies": [
            {"repo_url": f"https://github.com/Test/{repo}", "version": "1.0.0"}]})


def test_dotted_plugin_dependency_remains_rejected() -> None:
    with pytest.raises(ValueError, match="GitHub repository"):
        PluginInfo.from_dict({**INFO.asdict(), "plugin_dependencies": [
            {"repo_url": "https://github.com/Test/Plugin.Core", "version": "1.0.0"}]})


def test_invalid_target_aborts_retrieval_and_registration_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert url.endswith("/v1.0.0/plugin.json")
        invalid: JsonObject = {**INFO.asdict(), "target": "both"}
        return response_fixture(json.dumps(invalid).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[FakeAsset()])]).as_github())
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert calls == ["https://raw.githubusercontent.com/Test/Plugin/v1.0.0/plugin.json"]
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()


def test_optional_icon_and_images_round_trip() -> None:
    info = replace(INFO, icon_url="https://example.com/icon.png", image_urls=["https://example.com/screenshot.png"])
    assert PluginInfo.from_dict(info.asdict()) == info
    release = replace(ENTRY, info=info)
    assert DllRelease.from_dict(release.asdict()) == release
    assert PluginInfo.from_dict(INFO.asdict()).icon_url is None
    assert PluginInfo.from_dict(INFO.asdict()).image_urls == []


@pytest.mark.parametrize("field,value", [("icon_url", "http://example.com/icon.png"), ("icon_url", "file:///icon.png"),
                                         ("icon_url", 5), ("icon_url", "https://user:password@example.com/icon.png"),
                                         ("image_urls", "https://example.com/image.png"), ("image_urls", [None]),
                                         ("image_urls", ["http://example.com/image.png"])])
def test_invalid_icon_and_images_are_rejected(field: str, value: JsonValue) -> None:
    data: JsonObject = {**INFO.asdict(), field: value}
    with pytest.raises(ValueError):
        PluginInfo.from_dict(data)


def test_registry_requires_registered_dependency_versions() -> None:
    info = replace(INFO, plugin_dependencies=[Dependency("https://github.com/Test/Other", ">=1.0.0,<2.0.0")])
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
    retriever.dll = replace(ENTRY, info=replace(INFO, plugin_dependencies=[Dependency("https://github.com/Test/Missing", "1.0.0")]))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0", dry_run=True)
    assert not Path(registry.dll_index_path).exists()
