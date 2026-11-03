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
from mod_registry_core.json_types import JsonObject
from tests.fakes import FakeRetriever, mod_fixture


@pytest.fixture()
def registry(tmp_path: Path) -> FilesystemPackageRegistry:
    fake = FakeRetriever()
    instance = FilesystemPackageRegistry(fake, str(tmp_path / "registry"), str(tmp_path / "package_db"), str(tmp_path / "dll_db"))
    fake.releases[("Test/Pak", "v1.0.0")] = mod_fixture("Pak").releases[0]
    assert instance.add_package_release(Repo("Test", "Pak"), "v1.0.0")
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
    with pytest.raises(ValueError, match="Unregistered") as failure:
        validate_metadata(path, kind, registry)
    assert str(path) in str(failure.value)


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


@pytest.mark.parametrize("kind", ["mod", "plugin"])
def test_metadata_cli_reports_all_schema_errors(
    tmp_path: Path, registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], kind: str,
) -> None:
    path = tmp_path / f"{kind}.json"
    data = metadata()
    del data["description"]
    data["authors"] = [False]
    data["plugin_dependencies"] = [{"repo_url": True, "version": "1.0.0"}]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "argv", ["validate-metadata", "--registry-directory", str(tmp_path), f"--{kind}-file", str(path)])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    error = capsys.readouterr().err
    for detail in [str(path), "description", "$.authors[0]", "$.plugin_dependencies[0].repo_url", "not of type 'string'"]:
        assert detail in error


@pytest.mark.parametrize("version,duplicate,field", [
    ("01.0.0", False, "plugin_dependencies[0].version"),
    ("1.0.0", True, "plugin_dependencies[1].repo_url"),
])
def test_metadata_cli_reports_source_for_semantic_errors(
    tmp_path: Path, registry: FilesystemPackageRegistry, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], version: str, duplicate: bool, field: str,
) -> None:
    path = tmp_path / "local-plugin.json"
    data = metadata()
    dependency: JsonObject = {"repo_url": "https://github.com/Test/Native", "version": version}
    data["plugin_dependencies"] = [dependency, {**dependency, "repo_url": "https://github.com/test/native", "version": "^1.0.0"}] if duplicate else [dependency]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "argv", ["validate-metadata", "--registry-directory", str(tmp_path), "--plugin-file", str(path)])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    error = capsys.readouterr().err
    assert str(path) in error
    assert field in error
    assert "Schema validation failed" not in error


def test_mod_registry_error_identifies_package_tag_and_field(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    instance = FilesystemPackageRegistry(registry_path=str(tmp_path / "registry"),
        package_db_path=str(tmp_path / "package_db"), dll_db_path=str(tmp_path / "dll_db"))
    path = Path(instance.packages_dir) / "Test/Pak.json"
    path.parent.mkdir(parents=True)
    data = mod_fixture("Pak").asdict()
    releases = data["releases"]
    assert isinstance(releases, list) and isinstance(releases[0], dict)
    info = releases[0]["info"]
    assert isinstance(info, dict)
    info["authors"] = [False]
    path.write_text(json.dumps(data))
    Path(instance.mod_list_index_path).write_text("Test/Pak\n")
    assert not instance.validate_package_db([])
    for detail in [str(path), "Test/Pak", "v1.0.0", "releases[0]", "authors[0]", "not of type 'string'"]:
        assert detail in caplog.text


def test_metadata_cli_rejects_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate-metadata", "--registry-directory", str(tmp_path)])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 2


def test_local_validation_needs_no_retriever_or_synthetic_identity(tmp_path: Path, registry: FilesystemPackageRegistry) -> None:
    local = FilesystemPackageRegistry(registry_path=str(tmp_path / "registry"),
        package_db_path=str(tmp_path / "package_db"), dll_db_path=str(tmp_path / "dll_db"))
    assert local.mod_retriever is None
    for kind in ("mod", "plugin"):
        path = tmp_path / f"{kind}.json"
        data = metadata()
        path.write_text(json.dumps(data))
        original = path.read_bytes()
        validate_metadata(path, kind, local)
        assert path.read_bytes() == original


def test_local_registry_construction_does_not_create_directories(tmp_path: Path) -> None:
    local = FilesystemPackageRegistry(registry_path=str(tmp_path / "registry"),
        package_db_path=str(tmp_path / "package_db"), dll_db_path=str(tmp_path / "dll_db"))
    assert not (tmp_path / "package_db").exists()
    assert not (tmp_path / "registry").exists()
    assert not local.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    assert not local.add_package_release(Repo("Test", "Pak"), "v1.0.0")
    assert not (tmp_path / "package_db").exists()


def test_composite_action_validation_step(tmp_path: Path, registry: FilesystemPackageRegistry) -> None:
    root = Path(__file__).resolve().parents[1]
    action_directory = root / "actions/validate-metadata"
    action = (action_directory / "action.yml").read_text()
    script = "\n".join(line[8:] for line in action.split("      run: |\n", 1)[1].splitlines())
    published = tmp_path / ".metadata-validation-registry"
    shutil.copytree(tmp_path / "package_db", published / "package_db")
    shutil.copytree(tmp_path / "dll_db", published / "dll_db")
    data = metadata()
    data["target"] = PluginTarget.CLIENT.value
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
