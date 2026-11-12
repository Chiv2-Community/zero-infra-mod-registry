from dataclasses import replace
import json
from pathlib import Path

import pytest
import requests

from generated_models.dependencies import Dependency
from generated_models.metadata import DllRelease, Plugin, PluginInfo, PluginTarget
from zero_infra_mod_registry.models.dll_metadata import plugin_from_dict, validate_dll_releases
from zero_infra_mod_registry.models.loading import load, serialize
from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from generated_models.json_types import JsonObject, decode_json, json_object
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, FakeRetriever, response_fixture

INFO = PluginInfo("Display name", "Description", ["Author"], [])
ENTRY = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", "a" * 64, 1, INFO)


def test_plugin_json_is_fetched_from_exact_release_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert timeout == 60
        return response_fixture(json.dumps(serialize(INFO)).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    result = GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), FakeRelease(tag_name="v1.0.0-RC2").as_release())
    assert result == replace(INFO, repo_url="https://github.com/Test/Plugin")
    assert calls == ["https://raw.githubusercontent.com/Test/Plugin/v1.0.0-RC2/plugin.json"]


@pytest.mark.parametrize("status,body", [(404, b"missing"), (200, b"invalid JSON")])
def test_missing_or_invalid_plugin_json_is_rejected(monkeypatch: pytest.MonkeyPatch, status: int, body: bytes) -> None:
    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(body, url, status)
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises((ValueError, requests.HTTPError)):
        GithubModMetadataRetriever(FakeGithub([]).as_github()).fetch_plugin_info(Repo("Test", "Plugin"), FakeRelease().as_release())


def test_registration_summary_identifies_metadata_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    data: JsonObject = {"name": "Plugin", "typo": True, "authors": [True],
                        "plugin_dependencies": [{"repo_url": True, "version": "1.0.0"}]}
    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(json.dumps(data).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[FakeAsset()])]).as_github())
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    for detail in ["Test/Plugin", "v1.0.0", "plugin.json", "description", "authors[0]", "plugin_dependencies[0].repo_url", "typo"]:
        assert detail in caplog.text


def test_registry_summary_identifies_invalid_stored_release(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    registry = FilesystemPackageRegistry(registry_path=str(tmp_path / "registry"),
        package_db_path=str(tmp_path / "packages"), dll_db_path=str(tmp_path / "dlls"))
    path = Path(registry.plugin_packages_dir) / "Test/Plugin.json"
    path.parent.mkdir(parents=True)
    release = serialize(ENTRY)
    del release["hash"]
    release["unexpected"] = True
    package: JsonObject = {"latest_release_info": serialize(INFO), "releases": [release]}
    path.write_text(json.dumps(package))
    Path(registry.plugin_list_index_path).write_text("Test/Plugin\n")
    assert not registry.validate_dll_db()
    for detail in [str(path), "Test/Plugin", "1.0.0", "releases[0]", "'hash' is a required property", "'unexpected' was unexpected"]:
        assert detail in caplog.text


def test_latest_metadata_mismatch_names_package_release_and_fields() -> None:
    data = serialize(Plugin([ENTRY]))
    data["latest_release_info"] = serialize(replace(INFO, name="Wrong name", description="Wrong description"))
    with pytest.raises(ValueError) as failure:
        plugin_from_dict("Test", "Plugin", data)
    for detail in ["Test/Plugin", "1.0.0", "latest_release_info.name", "latest_release_info.description"]:
        assert detail in str(failure.value)


def test_legacy_plugin_metadata_without_target_defaults_to_shared() -> None:
    data = serialize(INFO)
    del data["target"]
    assert load(data, PluginInfo).target is PluginTarget.SHARED
    package = serialize(Plugin([ENTRY]))
    latest = json_object(package["latest_release_info"])
    del latest["target"]
    package["latest_release_info"] = latest
    release = serialize(ENTRY)
    release["info"] = data
    package["releases"] = [release]
    assert plugin_from_dict("Test", "Plugin", package).releases == [replace(ENTRY, tag="1.0.0")]


@pytest.mark.parametrize("uploaded", [False, True])
@pytest.mark.parametrize("tag", ["v1.0.0", "1.0.0", "v1.0.0-rc.1", "v1.0.0+build.42", "v1.0.0-rc.1+build.42"])
@pytest.mark.parametrize("version_prefix", [None, "", "v"])
def test_retrieval_and_registration_preserve_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploaded: bool, tag: str, version_prefix: str | None,
) -> None:
    binary = b"DLL bytes"
    data = serialize(INFO)
    data["target"] = PluginTarget.CLIENT.value
    version = None if version_prefix is None else version_prefix + tag.removeprefix("v")
    if version is not None:
        data["version"] = version
    metadata_url = "https://example.com/plugin.json" if uploaded else f"https://raw.githubusercontent.com/Test/Plugin/{tag}/plugin.json"
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
    client = FakeGithub([FakeRelease(tag_name=tag, assets=assets)])
    retriever = GithubModMetadataRetriever(client.as_github())
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert registry.add_dll_release(Repo("Test", "Plugin"), tag)
    package = json_object(decode_json((Path(registry.plugin_packages_dir) / "Test/Plugin.json").read_text()))
    expected = PluginTarget.CLIENT
    assert json_object(package["latest_release_info"])["target"] == expected.value
    restored = plugin_from_dict("Test", "Plugin", package)
    assert restored.releases[0].info is not None
    assert restored.releases[0].info.target is expected
    assert restored.releases[0].info.version == version
    assert restored.releases[0].tag == tag
    assert restored.releases[0].version == tag.removeprefix("v")
    assert "manifest" not in serialize(restored.releases[0])
    assert registry.validate_dll_db(verify_downloads=True)
    assert calls == [metadata_url, ENTRY.download_url, ENTRY.download_url]


def test_invalid_target_aborts_retrieval_and_registration_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert url.endswith("/v1.0.0/plugin.json")
        invalid: JsonObject = {**serialize(INFO), "target": "both"}
        return response_fixture(json.dumps(invalid).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[FakeAsset()])]).as_github())
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert calls == ["https://raw.githubusercontent.com/Test/Plugin/v1.0.0/plugin.json"]
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()


def test_registry_requires_registered_dependency_versions() -> None:
    info = replace(INFO, plugin_dependencies=[Dependency("https://github.com/Test/Other", ">=1.0.0,<2.0.0")])
    plugin = replace(ENTRY, info=info)
    dependency = replace(ENTRY, name="Other")
    validate_dll_releases([plugin, dependency])
    with pytest.raises(ValueError, match="Unregistered plugin dependency"):
        validate_dll_releases([plugin])
    with pytest.raises(ValueError, match="Unregistered plugin dependency"):
        validate_dll_releases([plugin, replace(dependency, version="2.0.0")])


def test_new_registration_requires_info_and_does_not_write_on_failure(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    retriever.dll = replace(ENTRY, info=None)
    registry = FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "packages"), str(tmp_path / "dlls"))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()
    retriever.dll = replace(ENTRY, info=replace(INFO, plugin_dependencies=[Dependency("https://github.com/Test/Missing", "1.0.0")]))
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0", dry_run=True)
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()
