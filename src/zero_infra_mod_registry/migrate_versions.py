"""Backfill stored package metadata versions from release tags, without downloads."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

from generated_models.json_types import JsonObject, decode_json, json_array, json_object, json_string
from generated_models.metadata import Mod, ModInfo, PluginInfo, PluginPackage
from zero_infra_mod_registry.models.loading import load
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.validation_errors import validation_context
from zero_infra_mod_registry.utils.version_requirements import parse_release_version, validate_metadata_version


def _timestamp(date: datetime | None) -> float:
    if date is None:
        return float("-inf")
    return (date if date.tzinfo is not None else date.replace(tzinfo=UTC)).timestamp()


def migrate_package(data: JsonObject, *, plugin: bool) -> int:
    """Change only version fields; reject inconsistent metadata before returning."""
    infos: list[ModInfo | PluginInfo | None]
    dates: list[datetime | None]
    latest_info: ModInfo | PluginInfo
    if plugin:
        package = load(data, PluginPackage)
        infos = [release.info for release in package.releases]
        dates = [release.release_date for release in package.releases]
        latest_info = package.latest_release_info
    else:
        mod = load(data, Mod)
        infos = [release.info for release in mod.releases]
        dates = [release.release_date for release in mod.releases]
        latest_info = mod.latest_release_info
    candidates = [index for index, info in enumerate(infos) if info is not None]
    if not candidates:
        raise ValueError("No release metadata for latest_release_info")
    def release_timestamp(index: int) -> float:
        return _timestamp(dates[index])

    # Registration selects the newest metadata-bearing release by publication date.
    latest_index = max(candidates, key=release_timestamp)
    expected = infos[latest_index]
    assert expected is not None
    if replace(latest_info, version=None) != replace(expected, version=None):
        raise ValueError("latest_release_info does not match the newest release metadata")

    changed = 0
    releases = [json_object(value) for value in json_array(data["releases"])]
    for index, release in enumerate(releases):
        tag = json_string(release["tag"])
        with validation_context(f"releases[{index}] {tag!r}"):
            version = str(parse_release_version(tag))
            info = infos[index]
            if info is None:
                continue
            validate_metadata_version(info.version, tag)
            if info.version is None:
                json_object(release["info"])["version"] = version
                changed += 1
    tag = json_string(releases[latest_index]["tag"])
    with validation_context("latest_release_info"):
        validate_metadata_version(latest_info.version, tag)
        if latest_info.version is None:
            json_object(data["latest_release_info"])["version"] = str(parse_release_version(tag))
            changed += 1
    return changed


def migrate_registry(root: Path, *, write: bool = False) -> dict[Path, int]:
    """Preflight every package, then optionally write the complete migration plan."""
    if not root.is_dir():
        raise ValueError(f"Registry directory does not exist: {root}")
    updates: dict[str, str] = {}
    counts: dict[Path, int] = {}
    for directory, plugin in [("package_db", False), ("dll_db", True)]:
        for path in sorted((root / directory / "packages").glob("*/*.json")):
            with validation_context(str(path)):
                data = json_object(decode_json(path.read_text()))
                changed = migrate_package(data, plugin=plugin)
                if changed:
                    updates[str(path)] = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
                    counts[path] = changed
    if not any((root / directory / "packages").is_dir() for directory in ("package_db", "dll_db")):
        raise ValueError("Expected package_db/packages or dll_db/packages")
    if write and updates:
        registry = FilesystemPackageRegistry(registry_path=str(root / "registry"),
            package_db_path=str(root / "package_db"), dll_db_path=str(root / "dll_db"))
        registry._write_registry_files(updates)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-directory", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="Apply changes; default is a dry run")
    args = parser.parse_args()
    root: Path = args.registry_directory
    write: bool = args.write
    try:
        counts = migrate_registry(root, write=write)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Version migration failed: {error}\n")
    for path, count in counts.items():
        print(f"{path}: {count} version field(s)")
    print(f"{'Updated' if write else 'Would update'} {len(counts)} package(s), {sum(counts.values())} version field(s)")
    if not write:
        print("Dry run; use --write to apply.")


if __name__ == "__main__":
    main()
