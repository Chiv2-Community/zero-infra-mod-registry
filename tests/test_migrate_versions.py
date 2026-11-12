"""Offline version backfill against the unchanged C2ModRegistry snapshot."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
import tarfile

import pytest

from generated_models.json_types import decode_json, json_array, json_object
from zero_infra_mod_registry.migrate_versions import main, migrate_package, migrate_registry
from zero_infra_mod_registry.models.loading import serialize
from tests.fakes import mod_fixture
from tests.test_registry_reference import ARCHIVE, COMMIT, SHA256


def test_reference_migration_is_offline_preserves_data_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == SHA256
    with tarfile.open(ARCHIVE) as archive:
        archive.extractall(tmp_path, filter="data")
    root = tmp_path / f"C2ModRegistry-{COMMIT}"
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def blocked(connection: socket.socket, address: str | tuple[str, int] | tuple[str, int, int, int]) -> None:
        raise AssertionError("Migration must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    planned = migrate_registry(root)
    assert len(planned) == 20
    assert sum(planned.values()) == 65  # 45 releases plus 20 latest metadata records.
    assert {path: path.read_bytes() for path in before} == before
    assert migrate_registry(root, write=True) == planned
    migrated = {path: path.read_bytes() for path in before}
    for path, original in before.items():
        if path not in planned:
            assert path.read_bytes() == original
            continue
        data = json_object(decode_json(path.read_text()))
        releases = [json_object(value) for value in json_array(data["releases"])]
        for release in releases:
            info = json_object(release["info"])
            assert info.pop("version") == str(release["tag"]).removeprefix("v")
        latest = json_object(data["latest_release_info"])
        assert latest.pop("version") == str(releases[0]["tag"]).removeprefix("v")
        assert data == decode_json(original.decode())
    assert migrate_registry(root, write=True) == {}
    assert {path: path.read_bytes() for path in before} == migrated

    # The normal registry validator still accepts the migrated database offline.
    from zero_infra_mod_registry.main import main as registry_main
    monkeypatch.setenv("GITHUB_TOKEN", "unused-migration-test")
    monkeypatch.setenv("VERIFY_DLL_DOWNLOADS", "false")
    monkeypatch.setattr(sys, "argv", ["registry", "--registry-path", str(root / "registry"),
        "--package-db-path", str(root / "package_db"), "--dll-db-path", str(root / "dll_db"), "validate"])
    registry_main()


def test_latest_version_uses_publication_date_not_list_order() -> None:
    data = serialize(mod_fixture(tag="v1.2.3-rc.1+build.42", date=datetime(2026, 11, 12)))
    older = serialize(mod_fixture(tag="v1.0.0", date=datetime(2026, 11, 11)).releases[0])
    releases = json_array(data["releases"])
    releases.insert(0, older)
    before = deepcopy(data)
    assert migrate_package(data, plugin=False) == 3
    assert json_object(data["latest_release_info"])["version"] == "1.2.3-rc.1+build.42"
    for value, original in zip(json_array(data["releases"]), json_array(before["releases"]), strict=True):
        info = json_object(json_object(value)["info"])
        assert info["version"] == str(json_object(value)["tag"]).removeprefix("v")
        info["version"] = None
        assert value == original


@pytest.mark.parametrize("field,value", [("tag", "invalid"), ("tag", "v1.0.0\n"),
    ("version", "2.0.0"), ("version", "v1.0.0"), ("latest_version", "2.0.0")])
def test_preflight_failure_does_not_write_any_packages(tmp_path: Path, field: str, value: str) -> None:
    directory = tmp_path / "package_db/packages/Test"
    directory.mkdir(parents=True)
    good = directory / "A.json"
    bad = directory / "Z.json"
    data = serialize(mod_fixture())
    good.write_text(json.dumps(data))
    if field == "tag":
        json_object(json_array(data["releases"])[0])["tag"] = value
    elif field == "version":
        json_object(json_object(json_array(data["releases"])[0])["info"])["version"] = value
    else:
        json_object(data["latest_release_info"])["version"] = value
    bad.write_text(json.dumps(data))
    before = {path: path.read_bytes() for path in (good, bad)}
    with pytest.raises(ValueError, match="Z.json"):
        migrate_registry(tmp_path, write=True)
    assert {path: path.read_bytes() for path in before} == before


def test_existing_versions_and_extra_fields_are_preserved() -> None:
    data = serialize(mod_fixture(tag="v1.0.0+build"))
    info = json_object(json_object(json_array(data["releases"])[0])["info"])
    info["version"] = "1.0.0+build"
    data["extra"] = {"version": "not release metadata"}
    assert migrate_package(data, plugin=False) == 1
    assert info["version"] == "1.0.0+build"
    assert data["extra"] == {"version": "not release metadata"}


def test_cli_defaults_to_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    directory = tmp_path / "package_db/packages/Test"
    directory.mkdir(parents=True)
    path = directory / "Mod.json"
    path.write_text(json.dumps(serialize(mod_fixture())))
    original = path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["migrate_versions", "--registry-directory", str(tmp_path)])
    main()
    assert "Would update 1 package(s), 2 version field(s)" in capsys.readouterr().out
    assert path.read_bytes() == original
    monkeypatch.setattr(sys, "argv", ["migrate_versions", "--registry-directory", str(tmp_path), "--write"])
    main()
    assert "Updated 1 package(s), 2 version field(s)" in capsys.readouterr().out
    assert path.read_bytes() != original


def test_invalid_registry_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected package_db"):
        migrate_registry(tmp_path)
