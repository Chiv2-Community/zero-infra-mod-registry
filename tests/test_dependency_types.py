from dataclasses import replace
from pathlib import Path
import json

import pytest

from zero_infra_mod_registry.metadata_validation import validate_metadata
from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo
from zero_infra_mod_registry.models.mod_metadata import Dependency, Mod, ModInfo, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from mod_registry_core.json_types import JsonObject, decode_json, json_array, json_object
from tests.fakes import FakeRetriever, mod_fixture


def test_old_mod_dependencies_are_normalized_and_both_fields_are_preserved() -> None:
    data: JsonObject = {"repo_url": "https://github.com/Test/Pak", "name": "Pak", "description": "Description", "authors": ["Author"],
                        "dependencies": [{"repo_url": "https://github.com/Test/OldPak", "version": "1.0.0"}],
                        "mod_dependencies": [{"repo_url": "https://github.com/Test/NewPak", "version": ">=1.0.0"}],
                        "plugin_dependencies": [{"repo_url": "https://github.com/Test/Native", "version": "^1.0.0"}]}
    info = ModInfo.from_dict(data)
    assert {dependency.repo_url for dependency in info.mod_dependencies} == {"https://github.com/Test/OldPak", "https://github.com/Test/NewPak"}
    assert info.plugin_dependencies == [Dependency("https://github.com/Test/Native", "^1.0.0")]
    assert info.asdict()["dependencies"] == info.asdict()["mod_dependencies"]
    assert ModInfo.from_dict(info.asdict()) == info


@pytest.mark.parametrize("with_dependencies", [False, True])
def test_every_serialized_release_mirrors_pak_dependencies(with_dependencies: bool) -> None:
    original = mod_fixture()
    dependencies = [Dependency("https://github.com/Test/Pak", "^1.0.0")] if with_dependencies else []
    old_info = replace(original.latest_release_info, mod_dependencies=dependencies)
    latest_info = replace(old_info,
                          plugin_dependencies=[Dependency("https://github.com/Test/Native", "^2.0.0")])
    mod = Mod(latest_info, [replace(original.releases[0], info=old_info),
                           replace(original.releases[0], tag="v2.0.0", info=latest_info)])
    data = mod.asdict()
    infos = [json_object(data["latest_release_info"])]
    infos.extend(json_object(json_object(release)["info"]) for release in json_array(data["releases"]))
    for info in infos:
        assert info["dependencies"] == info["mod_dependencies"] == [dep.asdict() for dep in dependencies]
    assert Mod.from_dict(data) == mod


def test_registration_writes_alias_for_existing_and_new_releases(tmp_path: Path) -> None:
    fake = FakeRetriever()
    registry = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    pak = mod_fixture("Pak")
    fake.releases[("Test/Pak", "v1.0.0")] = pak.releases[0]
    assert registry.add_package_release(Repo("Test", "Pak"), "v1.0.0")
    consumer = mod_fixture("Consumer")
    info = replace(consumer.latest_release_info, mod_dependencies=[Dependency("https://github.com/Test/Pak", "^1.0.0")])
    fake.releases[("Test/Consumer", "v1.0.0")] = replace(consumer.releases[0], info=info)
    assert registry.add_package_release(Repo("Test", "Consumer"), "v1.0.0")
    path = tmp_path / "package_db/packages/Test/Consumer.json"
    # Simulate an older registry file that omitted the compatibility alias.
    data = json_object(decode_json(path.read_text()))
    del json_object(data["latest_release_info"])["dependencies"]
    for release in json_array(data["releases"]):
        del json_object(json_object(release)["info"])["dependencies"]
    path.write_text(json.dumps(data))
    fake.releases[("Test/Consumer", "v2.0.0")] = replace(consumer.releases[0], tag="v2.0.0", info=info)
    assert registry.add_package_release(Repo("Test", "Consumer"), "v2.0.0")
    data = json_object(decode_json(path.read_text()))
    infos = [json_object(data["latest_release_info"])]
    infos.extend(json_object(json_object(release)["info"]) for release in json_array(data["releases"]))
    assert len(infos) == 3
    for serialized_info in infos:
        assert serialized_info["dependencies"] == serialized_info["mod_dependencies"] == [
            {"repo_url": "https://github.com/Test/Pak", "version": "^1.0.0"}]


def test_dependency_types_are_checked_against_their_own_registry(tmp_path: Path) -> None:
    fake = FakeRetriever()
    registry = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    native = DllRelease("Test", "Native", "1.0.0", "https://example.com/Native.dll", "a" * 64, 1,
                        PluginInfo("Native", "Description", ["Author"], []))
    fake.dll = native
    assert registry.add_dll_release(Repo("Test", "Native"), "v1.0.0")
    pak = mod_fixture("Pak")
    info = replace(pak.latest_release_info, plugin_dependencies=[Dependency("https://github.com/Test/Native", ">=1.0.0,<2.0.0")])
    fake.releases[("Test/Pak", "v1.0.0")] = replace(pak.releases[0], info=info)
    assert registry.add_package_release(Repo("Test", "Pak"), "v1.0.0")
    both = PluginInfo("Both", "Description", ["Author"], [Dependency("https://github.com/Test/Native", "1.0.0")],
                      mod_dependencies=[Dependency("https://github.com/Test/Pak", "1.0.0")])
    fake.dll = replace(native, name="Both", info=both)
    assert registry.add_dll_release(Repo("Test", "Both"), "v1.0.0")
    assert registry.validate_dll_db()
    assert registry.validate_package_db([])

    # A DLL entry cannot satisfy a mod dependency, even with the same repo/version.
    fake.dll = replace(native, name="WrongType", info=replace(both, mod_dependencies=[Dependency("https://github.com/Test/Native", "1.0.0")]))
    assert not registry.add_dll_release(Repo("Test", "WrongType"), "v1.0.0", dry_run=True)
    assert not registry.add_dll_release(Repo("Test", "WrongType"), "v1.0.0")

    missing = replace(info, plugin_dependencies=[Dependency("https://github.com/Test/Pak", "1.0.0")])
    assert not registry.validate_package_db([Mod(missing, [replace(pak.releases[0], info=missing)])])


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_dotted_pak_dependencies_validate_and_register(tmp_path: Path, kind: str) -> None:
    fake = FakeRetriever()
    registry = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    fake.releases[("Test/Pak.Core", "v1.0.0")] = mod_fixture("Pak.Core").releases[0]
    assert registry.add_package_release(Repo("Test", "Pak.Core"), "v1.0.0")
    data: JsonObject = {"name": "Consumer", "description": "Description", "authors": ["Author"],
                        "mod_dependencies": [{"repo_url": "https://github.com/Test/Pak.Core", "version": "1.0.0"}]}
    path = tmp_path / f"{kind}.json"
    path.write_text(json.dumps(data))
    validate_metadata(path, kind, registry)
    if kind == "plugin":
        fake.dll = DllRelease("Test", "Consumer", "1.0.0", "https://example.com/Consumer.dll", "a" * 64, 1,
                              PluginInfo.from_dict(data))
        assert registry.add_dll_release(Repo("Test", "Consumer"), "v1.0.0")
        assert registry.validate_dll_db()
    else:
        pak = mod_fixture("Consumer")
        data["repo_url"] = "https://github.com/Test/Consumer"
        info = ModInfo.from_dict(data)
        fake.releases[("Test/Consumer", "v1.0.0")] = replace(pak.releases[0], info=info)
        assert registry.add_package_release(Repo("Test", "Consumer"), "v1.0.0")
    assert registry.validate_package_db([])
