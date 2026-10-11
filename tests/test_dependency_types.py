from dataclasses import replace
from pathlib import Path

from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo
from zero_infra_mod_registry.models.mod_metadata import Dependency, Mod, ModInfo, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.json_types import JsonObject
from tests.fakes import FakeRetriever, mod_fixture


def test_old_mod_dependencies_are_normalized_and_both_fields_are_preserved() -> None:
    data: JsonObject = {"repo_url": "https://github.com/Test/Pak", "name": "Pak", "description": "Description", "authors": ["Author"],
                        "dependencies": [{"repo_url": "https://github.com/Test/OldPak", "version": "1.0.0"}],
                        "mod_dependencies": [{"repo_url": "https://github.com/Test/NewPak", "version": ">=1.0.0"}],
                        "plugin_dependencies": [{"repo_url": "https://github.com/Test/Native", "version": "^1.0.0"}]}
    info = ModInfo.from_dict(data)
    assert {dependency.repo_url for dependency in info.mod_dependencies} == {"https://github.com/Test/OldPak", "https://github.com/Test/NewPak"}
    assert info.plugin_dependencies == [Dependency("https://github.com/Test/Native", "^1.0.0")]
    assert "dependencies" not in info.asdict()
    assert ModInfo.from_dict(info.asdict()) == info


def test_dependency_types_are_checked_against_their_own_registry(tmp_path: Path) -> None:
    fake = FakeRetriever()
    registry = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    native = DllRelease("Test", "Native", "1.0.0", "https://example.com/Native.dll", "a" * 64, 1,
                        PluginInfo("Native", "Description", ["Author"], []))
    fake.dll = native
    assert registry.add_dll_release(Repo("Test", "Native"), "v1.0.0")
    pak = mod_fixture("Pak")
    info = replace(pak.latest_release_info, plugin_dependencies=[Dependency("https://github.com/Test/Native", ">=1.0.0,<2.0.0")])
    fake.mods["Test/Pak"] = Mod(info, [replace(pak.releases[0], info=info)])
    assert registry.add_package([Repo("Test", "Pak")]) == 1
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
