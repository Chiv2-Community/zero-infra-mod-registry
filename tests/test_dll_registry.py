import hashlib
from dataclasses import replace
from datetime import datetime
from github.GitRelease import GitRelease
import json
import os
from pathlib import Path
import stat
import sys

import pytest
import requests

from zero_infra_mod_registry.main import main
from zero_infra_mod_registry.models import DllRelease, Repo
from zero_infra_mod_registry.models.dll_metadata import Plugin, PluginInfo, validate_dll_entries, validate_dll_releases
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever, ModMetadataRetriever
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, decode_json
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, FakeRetriever, response_fixture

BINARY = b"registered DLL bytes"
INFO = PluginInfo("Plugin", "A native plugin", ["Author"], [])
DLL = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", hashlib.sha256(BINARY).hexdigest(), len(BINARY), INFO,
                 "v1.0.0", datetime(2023, 1, 1), "Release notes", "Plugin.dll")
ENTRY: JsonObject = DLL.asdict()


@pytest.fixture(autouse=True)
def plugin_info_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(self: GithubModMetadataRetriever, repo: Repo, release: GitRelease) -> PluginInfo:
        return INFO
    monkeypatch.setattr(GithubModMetadataRetriever, "fetch_plugin_info", fetch)


@pytest.fixture()
def retriever() -> FakeRetriever:
    fake = FakeRetriever()
    fake.dll = DLL
    fake.measurement = DLL.sha256, DLL.size
    return fake


@pytest.fixture()
def registry(tmp_path: Path, retriever: FakeRetriever) -> FilesystemPackageRegistry:
    return FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))


def test_metadata_and_duplicate_validation() -> None:
    assert validate_dll_entries([ENTRY]) == [DLL]
    duplicate: JsonObject = {**ENTRY, "organization": "TEST", "name": "PLUGIN"}
    with pytest.raises(ValueError, match="Duplicate"):
        validate_dll_entries([ENTRY, duplicate])


def test_typed_release_validation_does_not_reconstruct_models(monkeypatch: pytest.MonkeyPatch) -> None:
    def serialize(self: DllRelease) -> JsonObject:
        raise AssertionError("Domain validation must not serialize models")

    monkeypatch.setattr(DllRelease, "asdict", serialize)
    releases = [DLL]
    validate_dll_releases(releases)
    assert releases[0] is DLL
    with pytest.raises(ValueError, match="Duplicate"):
        validate_dll_releases([DLL, replace(DLL, organization="TEST")])


def test_registry_loading_validates_without_json_round_trip(registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")

    def serialize(self: DllRelease) -> JsonObject:
        raise AssertionError("Registry loading must not serialize parsed models")

    monkeypatch.setattr(DllRelease, "asdict", serialize)
    assert registry._load_dll_index() == [DLL]


@pytest.mark.parametrize("field,value", [
    ("organization", "../escape"), ("name", "bad.dll"), ("version", "latest"),
    ("download_url", "http://example.com/Plugin.dll"), ("download_url", "https://example.com/Plugin.pak"),
    ("download_url", "https://user:password@example.com/Plugin.dll"),
    ("sha256", "bad"), ("size", 0), ("size", True),
])
def test_invalid_metadata(field: str, value: JsonValue) -> None:
    invalid: JsonObject = {**ENTRY, field: value}
    with pytest.raises(ValueError):
        validate_dll_entries([invalid])


@pytest.mark.parametrize("entries", [None, {}, [None], [{}]])
def test_invalid_index(entries: JsonValue) -> None:
    with pytest.raises(ValueError):
        validate_dll_entries(entries)


def test_registration_separate_from_pak_index_and_immutable(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    path = Path(registry.plugin_packages_dir) / "Test/Plugin.json"
    assert decode_json(path.read_text()) == Plugin([DLL]).asdict()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    assert Path(registry.plugin_list_index_path).read_text() == "Test/Plugin\n"
    assert not Path(registry.dll_index_path).exists()
    assert not Path(registry.mod_list_index_path).exists()
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert decode_json(path.read_text()) == Plugin([DLL]).asdict()


def test_plugin_package_tracks_release_notes_and_latest_metadata(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    older = replace(DLL, version="0.9.0", tag="v0.9.0", release_date=datetime(2022, 1, 1),
                    release_notes_markdown="# Older notes", info=replace(INFO, name="Older name"))
    retriever.dll = older
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v0.9.0")
    path = Path(registry.plugin_packages_dir) / "Test/Plugin.json"
    data = decode_json(path.read_text())
    assert data == Plugin([DLL, older]).asdict()
    assert Plugin.from_dict("Test", "Plugin", data).releases == [DLL, older]
    assert "manifest" not in DLL.package_dict()
    assert DLL.package_dict()["release_notes_markdown"] == "Release notes"
    assert Path(registry.plugin_list_index_path).read_text() == "Test/Plugin\n"
    assert registry.validate_dll_db(verify_downloads=True)


def test_plugin_serialization_sorts_once_and_preserves_latest_info_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    first_info = replace(INFO, name="First tied release")
    first = replace(DLL, version="2.0.0", tag="v2.0.0", release_date=datetime(2024, 1, 1), info=first_info)
    second = replace(DLL, version="3.0.0", tag="v3.0.0", release_date=first.release_date, info=replace(INFO, name="Second tied release"))
    legacy = replace(DLL, version="4.0.0", tag="v4.0.0", release_date=datetime(2025, 1, 1), info=None)
    undated = replace(DLL, version="0.9.0", tag="v0.9.0", release_date=None)
    plugin = Plugin([DLL, first, second, undated, legacy])
    original = Plugin.sorted_releases
    calls = 0

    def sorted_releases(self: Plugin) -> list[DllRelease]:
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(Plugin, "sorted_releases", sorted_releases)
    data = plugin.asdict()
    assert calls == 1
    assert data == {"latest_release_info": first_info.asdict(),
                    "releases": [release.package_dict() for release in [legacy, first, second, DLL, undated]]}
    assert plugin.latest_info() == first_info


def test_legacy_releases_are_preserved_when_adding_plugin_package(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    legacy = replace(DLL, info=None, tag=None, release_date=None, release_notes_markdown=None, dll_file_name=None)
    path = Path(registry.dll_index_path)
    path.parent.mkdir(parents=True)
    entries: JsonValue = [legacy.asdict()]
    path.write_text(json.dumps(entries))
    original = path.read_bytes()
    retriever.dll = replace(DLL, version="2.0.0", tag="v2.0.0")
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v2.0.0")
    assert registry.validate_dll_db(verify_downloads=True)
    assert path.read_bytes() == original
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v2.0.0")
    package = Plugin.from_dict("Test", "Plugin", decode_json((Path(registry.plugin_packages_dir) / "Test/Plugin.json").read_text()))
    assert len(package.releases) == 2
    assert package.releases[1].info is None


def test_conflicting_legacy_and_package_releases_fail_validation(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    entries: JsonValue = [replace(DLL, sha256="0" * 64).asdict()]
    Path(registry.dll_index_path).write_text(json.dumps(entries))
    assert not registry.validate_dll_db()


@pytest.mark.parametrize("index", ["../escape\n", "Test/Plugin\nTEST/PLUGIN\n"])
def test_invalid_plugin_package_index_is_rejected(registry: FilesystemPackageRegistry, index: str) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    Path(registry.plugin_list_index_path).write_text(index)
    assert not registry.validate_dll_db()


def test_plugin_package_rejects_inconsistent_latest_metadata() -> None:
    data = Plugin([DLL]).asdict()
    data["latest_release_info"] = replace(INFO, name="Incorrect").asdict()
    with pytest.raises(ValueError, match="latest-release"):
        Plugin.from_dict("Test", "Plugin", data)


def test_plugin_package_write_failure_rolls_back(registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    write = registry._write_text_atomic
    failed = False

    def fail_index_once(path: str, text: str) -> None:
        nonlocal failed
        if path == registry.plugin_list_index_path and not failed:
            failed = True
            raise OSError("Index write failed")
        write(path, text)

    monkeypatch.setattr(registry, "_write_text_atomic", fail_index_once)
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()
    assert not Path(registry.plugin_list_index_path).exists()


def test_dry_run_and_failed_retrieval_do_not_write(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0", dry_run=True)
    assert not Path(registry.dll_index_path).exists()
    retriever.dll_error = requests.HTTPError("not found")
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.dll_index_path).exists()


def test_validation_checks_metadata_and_download_integrity(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.validate_dll_db()
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert registry.validate_dll_db(verify_downloads=True)
    retriever.measurement = "0" * 64, DLL.size
    assert not registry.validate_dll_db(verify_downloads=True)
    invalid: JsonValue = [{**ENTRY, "size": 0}]
    Path(registry.dll_index_path).write_text(json.dumps(invalid))
    assert not registry.validate_dll_db()


def test_github_retriever_hashes_download_without_pak_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(assets=[FakeAsset(size=len(BINARY))])
    client = FakeGithub([release])
    retriever = GithubModMetadataRetriever(client.as_github())
    calls: list[str] = []

    def get(url: str, *, stream: bool, timeout: int) -> requests.Response:
        assert stream and timeout == 60
        calls.append(url)
        return response_fixture(BINARY, url)

    monkeypatch.setattr(requests, "get", get)
    assert retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0") == DLL
    assert calls == [DLL.download_url]


@pytest.mark.parametrize("draft,tag,count,size", [
    (True, "v1.0.0", 1, len(BINARY)), (False, "latest", 1, len(BINARY)),
    (False, "v1.0.0", 0, len(BINARY)), (False, "v1.0.0", 2, len(BINARY)),
    (False, "v1.0.0", 1, len(BINARY) + 1),
])
def test_github_retriever_rejects_invalid_release(monkeypatch: pytest.MonkeyPatch, draft: bool, tag: str, count: int, size: int) -> None:
    release = FakeRelease(tag_name=tag, draft=draft, assets=[FakeAsset(size=size)] * count)
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())

    def measure(url: str) -> tuple[str, int]:
        return DLL.sha256, DLL.size

    monkeypatch.setattr(retriever, "measure_dll", measure)
    with pytest.raises(ValueError):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), tag)


def test_download_rejects_insecure_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str, *, stream: bool, timeout: int) -> requests.Response:
        return response_fixture(BINARY, "http://example.com/Plugin.dll")

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(ValueError, match="Insecure"):
        GithubModMetadataRetriever(FakeGithub([]).as_github()).measure_dll(DLL.download_url)


@pytest.mark.parametrize("filename", ["Plugin.dll", "Plugin_dbg.dll"])
def test_multiple_assets_allow_exact_explicit_selection(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    assets = [FakeAsset(name=name, browser_download_url=f"https://example.com/{name}", size=len(BINARY))
              for name in ("Plugin.dll", "Plugin_dbg.dll")]
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=assets)]).as_github())
    downloaded: list[str] = []

    def measure(url: str) -> tuple[str, int]:
        downloaded.append(url)
        return DLL.sha256, DLL.size

    monkeypatch.setattr(retriever, "measure_dll", measure)
    result = retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0", filename)
    assert result.download_url == f"https://example.com/{filename}"
    assert downloaded == [result.download_url]


@pytest.mark.parametrize("filename", ["Missing.dll", "plugin.dll", "*.dll", "readme.txt", "", "../Plugin.dll"])
def test_explicit_selection_never_falls_back(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    release = FakeRelease(assets=[FakeAsset(), FakeAsset(name="readme.txt")])
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())

    def measure(url: str) -> tuple[str, int]:
        pytest.fail("A rejected selection must not download anything")

    monkeypatch.setattr(retriever, "measure_dll", measure)
    with pytest.raises(ValueError, match="Requested DLL asset"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0", filename)


def test_duplicate_asset_names_are_ambiguous() -> None:
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[FakeAsset(), FakeAsset()])]).as_github())
    with pytest.raises(ValueError, match="Requested DLL asset"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0", "Plugin.dll")


def test_no_assets_does_not_request_filename_selection() -> None:
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[])]).as_github())
    with pytest.raises(ValueError, match="no DLL assets"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0")


@pytest.mark.parametrize("contents", ["", "Existing", "Existing\n"])
def test_index_append_preserves_newlines(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "index.txt"
    path.write_text(contents)
    FilesystemPackageRegistry._append_index_entry(str(path), "New")
    assert path.read_text().splitlines() == (["Existing"] if contents else []) + ["New"]


def test_cli_passes_dll_options_and_propagates_errors(tmp_path: Path, retriever: FakeRetriever, monkeypatch: pytest.MonkeyPatch) -> None:
    locations: list[str] = []

    def build(mod_retriever: ModMetadataRetriever, registry_path: str, package_db_path: str, dll_db_path: str) -> FilesystemPackageRegistry:
        locations.append(dll_db_path)
        return FilesystemPackageRegistry(retriever, registry_path, package_db_path, dll_db_path)

    monkeypatch.setattr("zero_infra_mod_registry.main.FilesystemPackageRegistry", build)
    common = ["registry", "--github-token", "test", "--registry-path", str(tmp_path / "registry"),
              "--package-db-path", str(tmp_path / "packages"), "--dll-db-path", str(tmp_path / "dlls")]
    monkeypatch.setattr(sys, "argv", common + ["add-dll-release", "https://github.com/Test/Plugin", "v1.0.0", "--dll-file", "Plugin.dll"])
    main()
    assert retriever.dll_calls == [(Repo("Test", "Plugin"), "v1.0.0", "Plugin.dll")]
    assert locations == [str(tmp_path / "dlls")]
    assert decode_json((tmp_path / "dlls/packages/Test/Plugin.json").read_text()) == Plugin([DLL]).asdict()
    retriever.measurement = "0" * 64, DLL.size
    monkeypatch.setattr(sys, "argv", common + ["validate", "--verify-dll-downloads"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
