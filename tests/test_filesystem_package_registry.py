from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from zero_infra_mod_registry.models import Dependency, Mod, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from tests.fakes import FakeRetriever, mod_fixture


@pytest.fixture()
def retriever() -> FakeRetriever:
    fake = FakeRetriever()
    fake.mods["Test/Plugin"] = mod_fixture()
    return fake


@pytest.fixture()
def registry(tmp_path: Path, retriever: FakeRetriever) -> FilesystemPackageRegistry:
    return FilesystemPackageRegistry(retriever, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))


def test_load_package_list(registry: FilesystemPackageRegistry, tmp_path: Path) -> None:
    path = tmp_path / "index.txt"
    path.write_text("org1/repo1\norg2/repo2\norg3/repo3")
    assert registry._load_package_list(str(path)) == ["org1/repo1", "org2/repo2", "org3/repo3"]
    assert registry._load_package_list(str(tmp_path / "missing")) == []


def test_get_all_text_lines_in_directory(registry: FilesystemPackageRegistry) -> None:
    path = Path(registry.registry_path)
    path.mkdir()
    (path / "Test.txt").write_text("https://github.com/Test/Plugin\n# comment\n\nhttps://github.com/Test/Other\n")
    assert registry._get_all_text_lines_in_directory(str(path)) == ["https://github.com/Test/Plugin", "https://github.com/Test/Other"]


def test_generate_package_list(registry: FilesystemPackageRegistry) -> None:
    path = Path(registry.registry_path)
    path.mkdir()
    (path / "Test.txt").write_text("https://github.com/Test/Plugin\n")
    assert registry._generate_package_list(str(path)) == ["Test/Plugin"]


@pytest.mark.parametrize("url", ["https://github.com/org1/repo1", "org1/repo1", "https://github.com/org1/repo1/"])
def test_repo_to_index_entry(url: str) -> None:
    assert repo_to_index_entry(url) == "org1/repo1"


def test_is_package_initialized(registry: FilesystemPackageRegistry) -> None:
    assert not registry.is_package_initialized("Test", "Plugin")
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert registry.is_package_initialized("Test", "Plugin")


def test_load_mod(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()


def test_load_mod_file_not_found(registry: FilesystemPackageRegistry) -> None:
    assert registry.load_mod(Repo("Missing", "Plugin")) is None


def test_validate_package_db_empty(registry: FilesystemPackageRegistry) -> None:
    assert registry.validate_package_db([])


def test_process_registry_updates_with_dry_run(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    path = Path(registry.registry_path) / "Test.txt"
    path.write_text("")
    before = Path(registry.mod_list_index_path).read_text()
    assert registry.process_registry_updates(dry_run=True)
    assert Path(registry.mod_list_index_path).read_text() == before
    assert registry.load_mod(Repo("Test", "Plugin")) is not None


def test_process_registry_updates_adds_retrieved_package(registry: FilesystemPackageRegistry) -> None:
    path = Path(registry.registry_path)
    path.mkdir()
    (path / "Test.txt").write_text("https://github.com/Test/Plugin")
    assert registry.process_registry_updates()
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()


def test_process_registry_updates_propagates_retrieval_failure(registry: FilesystemPackageRegistry) -> None:
    path = Path(registry.registry_path)
    path.mkdir()
    (path / "Test.txt").write_text("https://github.com/Missing/Plugin")
    assert not registry.process_registry_updates()
    assert not Path(registry.mod_list_index_path).exists()


def test_add_release_fails_if_package_not_in_index(registry: FilesystemPackageRegistry) -> None:
    with pytest.raises(ValueError, match="not in the package list"):
        registry.add_package_release(Repo("Missing", "Plugin"), "v1.0.0")


def test_add_release_initializes_if_mod_not_found(registry: FilesystemPackageRegistry) -> None:
    Path(registry.mod_list_index_path).write_text("Test/Plugin\n")
    assert registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()


def test_add_release_fetches_release_metadata(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    release = replace(mod_fixture().releases[0], tag="v2.0.0")
    retriever.releases[release.tag] = release
    before = Path(registry.packages_dir, "Test/Plugin.json").read_bytes()
    assert registry.add_package_release(Repo("Test", "Plugin"), release.tag, dry_run=True)
    assert retriever.release_calls == [(mod_fixture(), release.tag)]
    assert Path(registry.packages_dir, "Test/Plugin.json").read_bytes() == before
    assert registry.add_package_release(Repo("Test", "Plugin"), release.tag)
    loaded = registry.load_mod(Repo("Test", "Plugin"))
    assert loaded is not None and release in loaded.releases


def test_add_release_skips_existing_tag(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert not registry.add_package_release(Repo("Test", "Plugin"), "v1.0.0")
    assert retriever.release_calls == []


def test_init_creates_package_file_and_registry_entry(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert Path(registry.mod_list_index_path).read_text() == "Test/Plugin\n"
    assert Path(registry.registry_path, "Test.txt").read_text() == "https://github.com/Test/Plugin\n"
    assert registry.load_mod(Repo("Test", "Plugin")) == mod_fixture()


def test_init_dry_run(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")], dry_run=True) == 1
    assert not Path(registry.mod_list_index_path).exists()
    assert not Path(registry.packages_dir, "Test/Plugin.json").exists()


def test_init_with_existing_registry_entry(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert Path(registry.mod_list_index_path).read_text().splitlines() == ["Test/Plugin"]


def test_init_with_failed_repo_metadata_fetch(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Missing", "Plugin")]) == 0
    assert not Path(registry.mod_list_index_path).exists()


def test_init_multiple_repos(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    retriever.mods["Test/Other"] = mod_fixture("Other")
    assert registry.add_package([Repo("Test", "Plugin"), Repo("Test", "Other")]) == 2
    assert Path(registry.mod_list_index_path).read_text().splitlines() == ["Test/Plugin", "Test/Other"]
    assert registry.load_mod(Repo("Test", "Other")) == mod_fixture("Other")


def test_remove_mods(registry: FilesystemPackageRegistry) -> None:
    assert registry.add_package([Repo("Test", "Plugin")]) == 1
    assert registry.remove_mods([Repo("Test", "Plugin")], dry_run=True)
    assert registry.load_mod(Repo("Test", "Plugin")) is not None
    assert registry.remove_mods([Repo("Test", "Plugin")])
    assert not Path(registry.packages_dir, "Test").exists()


def test_remove_nonexistent_mod(registry: FilesystemPackageRegistry) -> None:
    assert not registry.remove_mods([Repo("Missing", "Plugin")])


def test_validation_rejects_missing_indexed_package(registry: FilesystemPackageRegistry) -> None:
    Path(registry.mod_list_index_path).write_text("Missing/Plugin\n")
    assert not registry.validate_package_db([])


def test_validation_rejects_missing_dependency(registry: FilesystemPackageRegistry, retriever: FakeRetriever) -> None:
    original = mod_fixture()
    info = replace(original.latest_release_info, mod_dependencies=[Dependency("https://github.com/Missing/Plugin", ">=1.0.0")])
    retriever.mods["Test/Plugin"] = Mod(info, [replace(original.releases[0], info=info)])
    assert registry.add_package([Repo("Test", "Plugin")]) == 0
    assert not Path(registry.mod_list_index_path).exists()
