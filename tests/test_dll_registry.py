import hashlib
import json
import os
from pathlib import Path
import stat
import sys

import pytest
import requests

from zero_infra_mod_registry.main import main
from zero_infra_mod_registry.models import DllRelease, Repo
from zero_infra_mod_registry.models.dll_metadata import validate_dll_entries
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever, ModMetadataRetriever
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, decode_json
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, FakeRetriever, response_fixture

BINARY = b"registered DLL bytes"
DLL = DllRelease("Test", "Plugin", "1.0.0", "https://example.com/Plugin.dll", hashlib.sha256(BINARY).hexdigest(), len(BINARY))
ENTRY: JsonObject = DLL.asdict()


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
    assert decode_json(Path(registry.dll_index_path).read_text()) == [ENTRY]
    assert stat.S_IMODE(os.stat(registry.dll_index_path).st_mode) == 0o644
    assert not Path(registry.mod_list_index_path).exists()
    assert not registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert decode_json(Path(registry.dll_index_path).read_text()) == [ENTRY]


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
    assert decode_json((tmp_path / "dlls/index.json").read_text()) == [ENTRY]
    retriever.measurement = "0" * 64, DLL.size
    monkeypatch.setattr(sys, "argv", common + ["validate", "--verify-dll-downloads"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
