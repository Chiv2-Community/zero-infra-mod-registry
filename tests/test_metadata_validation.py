import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from zero_infra_mod_registry.metadata_validation import main, validate_metadata
from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo, PluginTarget
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.json_types import JsonObject
from tests.fakes import FakeRetriever, mod_fixture


@pytest.fixture()
def registry(tmp_path: Path) -> FilesystemPackageRegistry:
    fake = FakeRetriever()
    instance = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    fake.mods["Test/Pak"] = mod_fixture("Pak")
    assert instance.add_package([Repo("Test", "Pak")]) == 1
    fake.dll = DllRelease("Test", "Native", "1.0.0", "https://example.com/Native.dll", "a" * 64, 1,
                          PluginInfo("Native", "Description", ["Author"], []))
    assert instance.add_dll_release(Repo("Test", "Native"), "v1.0.0")
    return instance


def metadata() -> JsonObject:
    return {"name": "Example", "description": "Description", "authors": ["Author"],
            "mod_dependencies": [{"repo_url": "https://github.com/Test/Pak", "version": "^1.0.0"}],
            "plugin_dependencies": [{"repo_url": "https://github.com/Test/Native", "version": ">=1.0.0,<2.0.0"}]}


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_metadata_validation_checks_both_dependency_types(tmp_path: Path, registry: FilesystemPackageRegistry, kind: str) -> None:
    path = tmp_path / f"{kind}.json"
    path.write_text(json.dumps(metadata()))
    validate_metadata(path, kind, registry)


@pytest.mark.parametrize("kind", ["mod", "plugin"])
@pytest.mark.parametrize("field,repo,version", [
    ("mod_dependencies", "Test/Missing", "1.0.0"),
    ("plugin_dependencies", "Test/Missing", "1.0.0"),
    ("mod_dependencies", "Test/Pak", ">=2.0.0"),
    ("plugin_dependencies", "Test/Native", ">=2.0.0"),
    ("mod_dependencies", "Test/Native", "1.0.0"),
    ("plugin_dependencies", "Test/Pak", "1.0.0"),
])
def test_metadata_validation_rejects_missing_incompatible_and_wrong_type_dependencies(
    tmp_path: Path, registry: FilesystemPackageRegistry, kind: str, field: str, repo: str, version: str,
) -> None:
    data = metadata()
    data[field] = [{"repo_url": f"https://github.com/{repo}", "version": version}]
    path = tmp_path / f"{kind}.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unregistered"):
        validate_metadata(path, kind, registry)


def test_metadata_cli_validates_both_files(tmp_path: Path, registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    mod, plugin = tmp_path / "mod.json", tmp_path / "plugin.json"
    mod.write_text(json.dumps(metadata()))
    plugin.write_text(json.dumps(metadata()))
    monkeypatch.setattr(sys, "argv", ["validate-metadata", "--registry-directory", str(tmp_path),
                                      "--mod-file", str(mod), "--plugin-file", str(plugin)])
    main()
    plugin.write_text("{}")
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1


def test_metadata_cli_rejects_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate-metadata", "--registry-directory", str(tmp_path)])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 2


@pytest.mark.parametrize("target", list(PluginTarget))
def test_composite_action_validation_step(tmp_path: Path, registry: FilesystemPackageRegistry, target: PluginTarget) -> None:
    root = Path(__file__).resolve().parents[1]
    action_directory = root / "actions/validate-metadata"
    action = (action_directory / "action.yml").read_text()
    script = "\n".join(line[8:] for line in action.split("      run: |\n", 1)[1].splitlines())
    published = tmp_path / ".metadata-validation-registry"
    shutil.copytree(tmp_path / "package_db", published / "package_db")
    shutil.copytree(tmp_path / "dll_db", published / "dll_db")
    data = metadata()
    data["target"] = target.value
    (tmp_path / "plugin.json").write_text(json.dumps(data))
    env = {**os.environ, "GITHUB_WORKSPACE": str(tmp_path), "GITHUB_ACTION_PATH": str(action_directory),
           "MOD_FILE": "", "PLUGIN_FILE": ""}
    valid = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert valid.returncode == 0, valid.stderr
    data["target"] = "both"
    (tmp_path / "plugin.json").write_text(json.dumps(data))
    invalid = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert invalid.returncode != 0
    (tmp_path / "plugin.json").unlink()
    missing = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert missing.returncode != 0
    env["PLUGIN_FILE"] = "missing-plugin.json"
    explicit_missing = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert explicit_missing.returncode != 0
