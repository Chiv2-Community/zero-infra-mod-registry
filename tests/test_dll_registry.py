import hashlib
from dataclasses import replace
from datetime import datetime
from github.GitRelease import GitRelease
import json
import logging
import os
from pathlib import Path
import stat
import sys

import pytest
import requests

from zero_infra_mod_registry.main import main
from zero_infra_mod_registry.models import DllRelease, Repo
from zero_infra_mod_registry.models.dll_metadata import Plugin, PluginInfo, validate_dll_releases
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever, ModMetadataRetriever
from mod_registry_core.json_types import decode_json
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, FakeRetriever, mod_fixture, response_fixture

BINARY = b"registered DLL bytes"
INFO = PluginInfo("Plugin", "A native plugin", ["Author"], [])
DLL = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", hashlib.sha256(BINARY).hexdigest(), len(BINARY), INFO,
                 "v1.0.0", datetime(2023, 1, 1), "Release notes", "Plugin.dll")


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


def test_duplicate_release_identity_is_case_insensitive() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_dll_releases([DLL, replace(DLL, organization="TEST", name="PLUGIN")])


@pytest.mark.parametrize("registered", [True, False])
@pytest.mark.parametrize("verify_downloads", [True, False])
def test_dll_verification_messages(
    registry: FilesystemPackageRegistry, caplog: pytest.LogCaptureFixture,
    registered: bool, verify_downloads: bool,
) -> None:
    if registered:
        assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    with caplog.at_level(logging.INFO):
        assert registry.validate_dll_db(verify_downloads=verify_downloads)
    if not verify_downloads:
        assert "DLL download verification skipped: not requested." in caplog.text
    elif not registered:
        assert "DLL download verification skipped: no registered DLL releases." in caplog.text
    else:
        assert "DLL download verification passed for 1 registered release(s)." in caplog.text
    assert ("DLL download verification passed" in caplog.text) == (registered and verify_downloads)


def test_failed_dll_verification_does_not_report_success(
    registry: FilesystemPackageRegistry, retriever: FakeRetriever, caplog: pytest.LogCaptureFixture,
) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    retriever.measurement = ("0" * 64, DLL.size)
    with caplog.at_level(logging.INFO):
        assert not registry.validate_dll_db(verify_downloads=True)
    assert "DLL content mismatch" in caplog.text
    assert "DLL download verification passed" not in caplog.text


@pytest.mark.parametrize("plugin_first", [True, False])
def test_same_repository_and_tag_registers_both_kinds_without_overwriting(
    registry: FilesystemPackageRegistry, retriever: FakeRetriever, plugin_first: bool,
) -> None:
    repo = Repo("Test", "Plugin")
    retriever.releases[(str(repo), "v1.0.0")] = mod_fixture().releases[0]
    if plugin_first:
        assert registry.add_dll_release(repo, "v1.0.0", dll_file="Plugin.dll")
        assert registry.add_package_release(repo, "v1.0.0")
    else:
        assert registry.add_package_release(repo, "v1.0.0")
        assert registry.add_dll_release(repo, "v1.0.0", dll_file="Plugin.dll")
    assert registry.load_mod(repo) == mod_fixture()
    assert registry._load_dll_releases() == [DLL]
    assert Path(registry.mod_list_index_path).read_text() == "Test/Plugin\n"
    assert Path(registry.plugin_list_index_path).read_text() == "Test/Plugin\n"
    assert registry.validate_package_db([])
    assert registry.validate_dll_db(verify_downloads=True)


def test_registration_separate_from_pak_index_and_immutable(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    path = Path(registry.plugin_packages_dir) / "Test/Plugin.json"
    assert decode_json(path.read_text()) == Plugin([DLL]).asdict()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    assert Path(registry.plugin_list_index_path).read_text() == "Test/Plugin\n"
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


def test_plugin_serialization_preserves_date_order_and_tie_selection() -> None:
    first_info = replace(INFO, name="First tied release")
    first = replace(DLL, version="2.0.0", tag="v2.0.0", release_date=datetime(2024, 1, 1), info=first_info)
    second = replace(DLL, version="3.0.0", tag="v3.0.0", release_date=first.release_date, info=replace(INFO, name="Second tied release"))
    undated = replace(DLL, version="0.9.0", tag="v0.9.0", release_date=None)
    plugin = Plugin([DLL, first, second, undated])
    data = plugin.asdict()
    assert data == {"latest_release_info": first_info.asdict(),
                     "releases": [release.package_dict() for release in [first, second, DLL, undated]]}
    assert plugin.latest_info() == first_info


def test_obsolete_index_is_not_loaded_or_migrated(registry: FilesystemPackageRegistry) -> None:
    path = Path(registry.plugin_list_index_path).with_name("index.json")
    path.parent.mkdir(parents=True)
    path.write_text('[{"organization":"Test","name":"OldPlugin","version":"1.0.0"}]')
    original = path.read_bytes()
    assert registry._load_dll_releases() == []
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert registry._load_dll_releases() == [DLL]
    assert path.read_bytes() == original


def test_duplicate_package_releases_fail_validation(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    path = Path(registry.plugin_packages_dir) / "Test/Plugin.json"
    path.write_text(json.dumps(Plugin([DLL, DLL]).asdict()))
    assert not registry.validate_dll_db()


@pytest.mark.parametrize("index", ["../escape\n", "Test/Plugin\nTEST/PLUGIN\n"])
def test_invalid_plugin_package_index_is_rejected(registry: FilesystemPackageRegistry, index: str) -> None:
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    Path(registry.plugin_list_index_path).write_text(index)
    assert not registry.validate_dll_db()


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
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()
    retriever.dll_error = requests.HTTPError("not found")
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.plugin_list_index_path).exists()
    assert not (Path(registry.plugin_packages_dir) / "Test/Plugin.json").exists()


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


def test_unfinished_second_dll_requires_selection_before_download(monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(assets=[FakeAsset(size=len(BINARY)), FakeAsset(name="Other.DLL", size=0)])
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())
    downloaded: list[str] = []

    def measure(url: str) -> tuple[str, int]:
        downloaded.append(url)
        return DLL.sha256, DLL.size

    monkeypatch.setattr(retriever, "measure_dll", measure)
    with pytest.raises(ValueError, match="exactly one DLL"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not downloaded
    assert retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0", "Plugin.dll") == DLL
    assert downloaded == [DLL.download_url]


def test_duplicate_asset_names_are_ambiguous() -> None:
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[FakeAsset(), FakeAsset()])]).as_github())
    with pytest.raises(ValueError, match="Requested DLL asset"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0", "Plugin.dll")


def test_no_assets_does_not_request_filename_selection() -> None:
    retriever = GithubModMetadataRetriever(FakeGithub([FakeRelease(assets=[])]).as_github())
    with pytest.raises(ValueError, match="no DLL assets"):
        retriever.fetch_dll_release(Repo("Test", "Plugin"), "v1.0.0")


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
