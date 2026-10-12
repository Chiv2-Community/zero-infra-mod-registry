"""Validate repository metadata and its dependencies without downloading assets."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

from zero_infra_mod_registry.models.dll_metadata import PluginInfo
from zero_infra_mod_registry.models.mod_metadata import Dependency, dependencies_from_dict, mod_dependencies_from_dict
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.json_types import decode_json, json_object
from zero_infra_mod_registry.utils.version_requirements import parse_version_requirement


def metadata_validator(kind: str) -> Draft202012Validator:
    if kind not in {"mod", "plugin"}:
        raise ValueError("Metadata kind must be mod or plugin")
    schemas = Path(__file__).resolve().parent / "schemas"
    if not schemas.exists():
        schemas = Path(__file__).resolve().parents[2] / "schemas"
    schema = json_object(decode_json((schemas / f"{kind}.schema.json").read_text()))
    common = json_object(decode_json((schemas / "common.schema.json").read_text()))
    # Embedding the bundled resource under its $id resolves shared references
    # locally, without fetching the published schema URL.
    schema["$defs"] = {**json_object(schema.get("$defs", {})), "common": common}
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.check_schema(schema)
    return validator


def validate_metadata(path: Path, kind: str, registry: FilesystemPackageRegistry) -> None:
    validator = metadata_validator(kind)
    data = json_object(decode_json(path.read_text()))
    validator.validate(data)
    mod_dependencies: list[Dependency]
    plugin_dependencies: list[Dependency]
    if kind == "plugin":
        plugin = PluginInfo.from_dict(data)
        mod_dependencies, plugin_dependencies = plugin.mod_dependencies, plugin.plugin_dependencies
    else:
        mod_dependencies = mod_dependencies_from_dict(data)
        plugin_dependencies = dependencies_from_dict(data, "plugin_dependencies")
    for dependency in mod_dependencies + plugin_dependencies:
        parse_version_requirement(dependency.version)
    registry.validate_metadata_dependencies(mod_dependencies, plugin_dependencies)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-directory", required=True, type=Path)
    parser.add_argument("--mod-file", type=Path)
    parser.add_argument("--plugin-file", type=Path)
    args = parser.parse_args()
    registry_directory: Path = args.registry_directory
    mod_file: Path | None = args.mod_file
    plugin_file: Path | None = args.plugin_file
    files = [(path, kind) for path, kind in [(mod_file, "mod"), (plugin_file, "plugin")] if path is not None]
    if not files:
        parser.error("Specify --mod-file and/or --plugin-file")
    if not (registry_directory / "package_db/mod_list_index.txt").is_file():
        parser.error("Registry directory must contain package_db/mod_list_index.txt")
    registry = FilesystemPackageRegistry(registry_path=str(registry_directory / "registry"),
        package_db_path=str(registry_directory / "package_db"), dll_db_path=str(registry_directory / "dll_db"))
    try:
        for path, kind in files:
            validate_metadata(path, kind, registry)
            print(f"Validated {path} and its dependencies")
    except Exception as error:
        print(f"Metadata validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
