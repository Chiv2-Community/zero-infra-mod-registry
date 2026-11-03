"""Functional compatibility with an unchanged, pinned live-registry snapshot."""
import hashlib
from pathlib import Path
import socket
import sys
import tarfile

import pytest

from mod_registry_core.json_types import decode_json
from zero_infra_mod_registry.main import main
from zero_infra_mod_registry.models import Mod
from zero_infra_mod_registry.models.dll_metadata import Plugin

# Downloaded unchanged from this URL; tests never fetch a moving branch.
COMMIT = "1d3c56e3cbc85e7406b5a361831e1da3ad8f2da0"
SOURCE = f"https://codeload.github.com/Chiv2-Community/C2ModRegistry/tar.gz/{COMMIT}"
SHA256 = "e2e743d9dd1f0775d28b3a1c2c0ab3558cd0bef5e41dc3d0ce4f6c7a7b28a937"
ARCHIVE = Path(__file__).parent / "fixtures" / f"c2modregistry-{COMMIT}.tar.gz"


def test_pinned_c2modregistry_validates_and_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == SHA256, SOURCE
    with tarfile.open(ARCHIVE) as archive:
        archive.extractall(tmp_path, filter="data")
    root = tmp_path / f"C2ModRegistry-{COMMIT}"
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def blocked(connection: socket.socket, address: str | tuple[str, int] | tuple[str, int, int, int]) -> None:
        raise AssertionError("Reference validation must not fetch schemas, metadata, or binaries")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setenv("GITHUB_TOKEN", "unused-reference-test")
    monkeypatch.setenv("VERIFY_DLL_DOWNLOADS", "false")
    monkeypatch.setattr(sys, "argv", ["zero-infra-mod-registry", "--registry-path", str(root / "registry"),
        "--package-db-path", str(root / "package_db"), "--dll-db-path", str(root / "dll_db"), "validate"])
    main()

    mods = [Mod.from_dict(decode_json(path.read_text())) for path in sorted((root / "package_db/packages").rglob("*.json"))]
    plugins: list[Plugin] = []
    for path in sorted((root / "dll_db/packages").rglob("*.json")):
        plugin = Plugin.from_dict(path.parent.name, path.stem, decode_json(path.read_text()))
        assert Plugin.from_dict(path.parent.name, path.stem, plugin.asdict()) == plugin
        plugins.append(plugin)
    assert (len(mods), sum(len(mod.releases) for mod in mods)) == (19, 41)
    assert (len(plugins), sum(len(plugin.releases) for plugin in plugins)) == (1, 4)
    for mod in mods:
        assert Mod.from_dict(mod.asdict()) == mod
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
