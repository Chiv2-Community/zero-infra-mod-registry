"""DLL semantic checks and package adapters; fields are schema-generated."""
import re
from urllib.parse import urlparse

from semver import Version
from mod_registry_core.json_types import JsonObject, JsonValue, json_array, json_object
from generated_models.metadata import (
    DllRelease, Plugin, PluginInfo,
)
from zero_infra_mod_registry.utils.version_requirements import dependency_matches as dependency_matches, parse_version_requirement
from zero_infra_mod_registry.utils.validation_errors import validation_context
from zero_infra_mod_registry.utils.schema_validation import validate_schema
from zero_infra_mod_registry.models.loading import load, serialize


def validate_plugin_info(info: PluginInfo) -> None:
    validate_schema(serialize(info), "dll-metadata", "pluginInfo")
    validate_plugin_dependencies(info)


def validate_plugin_dependencies(info: PluginInfo) -> None:
    repos: set[tuple[str, str]] = set()
    dependencies = [("mod", index, dependency) for index, dependency in enumerate(info.mod_dependencies)]
    dependencies += [("plugin", index, dependency) for index, dependency in enumerate(info.plugin_dependencies)]
    for kind, index, dependency in dependencies:
        path = f"{kind}_dependencies[{index}]"
        key = kind, dependency.repo_url.lower()
        if key in repos:
            raise ValueError(f"{path}.repo_url: Duplicate plugin dependency")
        repos.add(key)
        with validation_context(f"{path}.version"):
            parse_version_requirement(dependency.version)


def dll_release_key(release: DllRelease) -> tuple[str, str, str]:
    return release.organization.lower(), release.name.lower(), release.version.lower()


def validate_dll_release(release: DllRelease) -> None:
    if release.info is not None:
        validate_plugin_info(release.info)
    for value in (release.organization, release.name):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid DLL organization/name")
    Version.parse(release.version)
    if release.tag is not None and str(Version.parse(release.tag.removeprefix("v"))) != release.version:
        raise ValueError("DLL tag/version mismatch")
    if release.info is not None and release.info.repo_url is not None and release.info.repo_url.lower() != f"https://github.com/{release.organization}/{release.name}".lower():
        raise ValueError("DLL metadata repository mismatch")
    url = urlparse(release.download_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or not url.path.lower().endswith(".dll") or url.fragment:
        raise ValueError("DLL source must be an HTTPS DLL URL")
    if not re.fullmatch(r"[a-f0-9]{64}", release.sha256):
        raise ValueError("Invalid DLL SHA-256")
    if isinstance(release.size, bool) or release.size <= 0:
        raise ValueError("Invalid DLL size")
    if release.dll_file_name is not None and (not release.dll_file_name.lower().endswith(".dll") or "/" in release.dll_file_name or "\\" in release.dll_file_name):
        raise ValueError("Invalid DLL asset filename")


def dll_package_dict(release: DllRelease) -> JsonObject:
    return {"tag": release.tag or release.version, "hash": release.sha256, "dll_file_name": release.dll_file_name,
            "download_url": release.download_url, "size": release.size,
            "release_date": release.release_date.isoformat() if release.release_date is not None else None,
            "info": serialize(release.info) if release.info is not None else None,
            "release_notes_markdown": release.release_notes_markdown}


def dll_from_package_dict(org: str, name: str, value: JsonValue) -> DllRelease:
    from generated_models.metadata import PluginRelease

    wire = load(value, PluginRelease)
    release = DllRelease(org, name, str(Version.parse(wire.tag.removeprefix("v"))), wire.download_url,
                         wire.hash, wire.size, wire.info, wire.tag, wire.release_date,
                         wire.release_notes_markdown, wire.dll_file_name)
    validate_dll_release(release)
    return release


def sorted_plugin_releases(plugin: Plugin) -> list[DllRelease]:
    def date(release: DllRelease) -> float:
        return release.release_date.timestamp() if release.release_date is not None else float("-inf")
    return sorted(plugin.releases, key=date, reverse=True)


def latest_plugin_info(plugin: Plugin) -> PluginInfo:
    releases = sorted_plugin_releases(plugin)
    if not releases or releases[0].info is None:
        raise ValueError("Plugin package has no metadata")
    return releases[0].info


def plugin_dict(plugin: Plugin) -> JsonObject:
    releases = sorted_plugin_releases(plugin)
    if not releases or releases[0].info is None:
        raise ValueError("Plugin package has no metadata")
    return {"latest_release_info": serialize(releases[0].info),
            "releases": [dll_package_dict(release) for release in releases]}


def plugin_from_dict(org: str, name: str, value: JsonValue) -> Plugin:
    with validation_context(f"{org}/{name}"):
        validate_schema(value, "registry", "plugin")
    data = json_object(value)
    with validation_context(f"{org}/{name} latest_release_info"):
        latest = load(data["latest_release_info"], PluginInfo)
    releases: list[DllRelease] = []
    for index, item in enumerate(json_array(data["releases"])):
        tag = item.get("tag", "unknown tag") if isinstance(item, dict) else "unknown tag"
        with validation_context(f"{org}/{name} {tag} releases[{index}]"):
            releases.append(dll_from_package_dict(org, name, item))
    plugin = Plugin(releases)
    expected = latest_plugin_info(plugin)
    if latest != expected:
        actual_fields, expected_fields = serialize(latest), serialize(expected)
        differences = sorted(key for key in actual_fields.keys() | expected_fields.keys()
                             if actual_fields.get(key) != expected_fields.get(key))
        latest_release = sorted_plugin_releases(plugin)[0]
        tag = latest_release.tag or latest_release.version
        raise ValueError(f"{org}/{name} {tag}: Plugin latest-release metadata mismatch in "
                         + ", ".join(f"latest_release_info.{key}" for key in differences))
    return plugin


def validate_dll_releases(releases: list[DllRelease]) -> None:
    for release in releases:
        validate_dll_release(release)
    keys = [dll_release_key(release) for release in releases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate DLL release")
    for release in releases:
        if release.info is None:
            raise ValueError("DLL releases require plugin.json metadata")
        for dependency in release.info.plugin_dependencies:
            org, name = urlparse(dependency.repo_url).path.strip("/").split("/")
            if org.lower() == dll_release_key(release)[0] and name.lower() == dll_release_key(release)[1]:
                raise ValueError("Plugin cannot depend on itself")
            if not any(dll_release_key(candidate)[0] == org.lower() and dll_release_key(candidate)[1] == name.lower() and dependency_matches(candidate.version, dependency.version)
                       for candidate in releases):
                raise ValueError(f"Unregistered plugin dependency: {dependency.repo_url} {dependency.version}")
