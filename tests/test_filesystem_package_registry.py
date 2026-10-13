from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from zero_infra_mod_registry.models import Dependency, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from tests.fakes import FakeRetriever, mod_fixture


@pytest.fixture()
def retriever() -> FakeRetriever:
    fake = FakeRetriever()
    fake.releases[("Test/Plugin", "v1.0.0")] = mod_fixture().releases[0]
    return fake


@pytest.fixture()
def registry(tmp_path: Path, retriever: FakeRetriever) -> FilesystemPackageRegistry:
    return FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))


def test_load_package_list(registry: FilesystemPackageRegistry, tmp_path: Path) -> None:
    path = tmp_path / "index.txt"
    path.write_text("org1/repo1\norg2/repo2\norg3/repo3")
    assert registry._load_package_list(str(path)) == ["org1/repo1", "org2/repo2", "org3/repo3"]
    assert registry._load_package_list(str(tmp_path / "missing")) == []


@pytest.mark.parametrize("url", ["https://github.com/org1/repo1", "org1/repo1", "https://github.com/org1/repo1/"])
def test_repo_to_index_entry(url: str) -> None:
    assert repo_to_index_entry(url) == "org1/repo1"


def test_load_mod(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()


def test_load_mod_file_not_found(registry: FilesystemPackageRegistry) -> None:
    assert registry.load_mod(Repo("Missing", "Plugin")) is None


def test_validate_package_db_empty(registry: FilesystemPackageRegistry) -> None:
    assert registry.validate_package_db([])


def test_first_release_creates_only_requested_release(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    retriever.releases[("Test/Plugin", "v2.0.0")] = mod_fixture(tag="v2.0.0").releases[0]
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert retriever.release_calls == [(Repo("Test", "Plugin"), "v1.0.0")]
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()
    assert Path(registry.mod_list_index_path).read_text() == "Test/Plugin\n"
    assert Path(registry.registry_path, "Test.txt").read_text() == "https://github.com/Test/Plugin\n"


def test_missing_indexed_mod_does_not_reimport(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    Path(registry.mod_list_index_path).write_text("Test/Plugin\n")
    assert not registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert retriever.release_calls == []
    assert registry.load_mod(Repo("Test", "Plugin")) is None


def test_add_release_fetches_release_metadata(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    retriever.release_calls.clear()
    release = replace(mod_fixture().releases[0], tag="v2.0.0")
    retriever.releases[("Test/Plugin", release.tag)] = release
    before = Path(registry.packages_dir, "Test/Plugin.json").read_bytes()
    assert registry.add_package_release(Repo("Test", "Plugin"), release.tag, dry_run=True)
    assert retriever.release_calls == [(Repo("Test", "Plugin"), release.tag)]
    assert Path(registry.packages_dir, "Test/Plugin.json").read_bytes() == before
    assert registry.add_package_release(Repo("Test", "Plugin"), release.tag)
    loaded = registry.load_mod(Repo("Test", "Plugin"))
    assert loaded is not None and release in loaded.releases and len(loaded.releases) == 2
    assert Path(registry.mod_list_index_path).read_text() == "Test/Plugin\n"


@pytest.mark.parametrize("tag", ["v1.0.0", "1.0.0"])
def test_add_release_skips_existing_version(registry: FilesystemPackageRegistry, retriever: FakeRetriever, tag: str) -> None:
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    retriever.release_calls.clear()
    assert not registry.add_package_release(Repo("Test", "Plugin"), tag)
    assert retriever.release_calls == []


def test_first_release_dry_run(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0", dry_run=True)
    assert not Path(registry.mod_list_index_path).exists()
    assert not Path(registry.packages_dir, "Test/Plugin.json").exists()
    assert not Path(registry.registry_path).exists()


def test_failed_release_fetch_does_not_write(registry: FilesystemPackageRegistry) -> None:
    assert not registry.add_package_release(Repo("Missing", "Plugin"), "v1.0.0")
    assert not Path(registry.mod_list_index_path).exists()


@pytest.mark.parametrize("repo", [Repo("..", "Plugin"), Repo("Test", ".."), Repo("Test", "../Other")])
def test_invalid_repository_does_not_fetch_or_write(registry: FilesystemPackageRegistry, retriever: FakeRetriever, repo: Repo) -> None:
    assert not registry.add_package_release(repo, "v1.0.0")
    assert retriever.release_calls == []
    assert not Path(registry.mod_list_index_path).exists()


@pytest.mark.parametrize("tag", ["v1.0.1", "invalid"])
def test_unavailable_or_invalid_tag_does_not_register_other_releases(registry: FilesystemPackageRegistry, tag: str) -> None:
    assert not registry.add_package_release(Repo("Test", "Plugin"), tag)
    assert registry.load_mod(Repo("Test", "Plugin")) is None
    assert not Path(registry.mod_list_index_path).exists()


def test_retrieved_release_must_match_requested_identity(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    retriever.releases[("Test/Plugin", "v1.0.0")] = mod_fixture("Other").releases[0]
    assert not registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.mod_list_index_path).exists()


def test_validation_rejects_missing_dependency(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    original = mod_fixture().releases[0]
    info = replace(original.info, mod_dependencies=[Dependency("https://github.com/Missing/Plugin", ">=1.0.0")])
    retriever.releases[("Test/Plugin", original.tag)] = replace(original, info=info)
    assert not registry.add_package_release(Repo("Test", "Plugin"), original.tag)
    assert not Path(registry.mod_list_index_path).exists()


def test_pak_registration_rolls_back_failed_index_write(registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    original_write = registry._write_text_atomic

    def fail_index(path: str, text: str) -> None:
        if path == registry.mod_list_index_path:
            raise OSError("Write failure")
        original_write(path, text)

    monkeypatch.setattr(registry, "_write_text_atomic", fail_index)
    assert not registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not Path(registry.mod_list_index_path).exists()
    assert registry.load_mod(Repo("Test", "Plugin")) is None


def test_remove_mods(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert registry.remove_mods([Repo("Test", "Plugin")], dry_run=True)
    assert registry.load_mod(Repo("Test", "Plugin")) is not None
    assert registry.remove_mods([Repo("Test", "Plugin")])
    assert not Path(registry.packages_dir, "Test").exists()


def test_remove_nonexistent_mod(registry: FilesystemPackageRegistry) -> None:
    assert not registry.remove_mods([Repo("Missing", "Plugin")])


def test_validation_rejects_missing_indexed_package(registry: FilesystemPackageRegistry) -> None:
    Path(registry.mod_list_index_path).write_text("Missing/Plugin\n")
    assert not registry.validate_package_db([])
