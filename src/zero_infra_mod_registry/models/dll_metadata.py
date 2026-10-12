"""Validated DLL metadata, independent of pak mod metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import List, Tuple
from urllib.parse import urlparse
from semver import Version
from zero_infra_mod_registry.models.mod_metadata import Dependency, dependencies_from_dict
from zero_infra_mod_registry.utils.version_requirements import dependency_matches as dependency_matches, parse_version_requirement

from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, json_array, json_int, json_object, json_string, optional_string, string_array


class PluginTarget(str, Enum):
    """Execution side declared by plugin.json, not a pak manifest."""

    SERVER = "server"
    CLIENT = "client"
    SHARED = "shared"


@dataclass(frozen=True)
class PluginInfo:
    name: str
    description: str
    authors: List[str]
    plugin_dependencies: List[Dependency]
    icon_url: str | None = None
    image_urls: List[str] = field(default_factory=list)
    mod_dependencies: List[Dependency] = field(default_factory=list)
    repo_url: str | None = None
    target: PluginTarget = PluginTarget.SHARED

    def validate(self) -> None:
        if not isinstance(self.target, PluginTarget):
            raise ValueError("Plugin target must be server, client or shared")
        if not self.name.strip() or not self.description.strip() or not self.authors or any(not author.strip() for author in self.authors):
            raise ValueError("plugin.json requires a name, description and authors")
        urls = self.image_urls + ([self.icon_url] if self.icon_url is not None else [])
        for image_url in urls:
            image = urlparse(image_url)
            if image.scheme != "https" or not image.hostname or image.username or image.password:
                raise ValueError("Plugin image/icon URLs must use HTTPS without credentials")
        repos: set[Tuple[str, str]] = set()
        for kind, dependency in [("mod", dependency) for dependency in self.mod_dependencies] + [("plugin", dependency) for dependency in self.plugin_dependencies]:
            url = urlparse(dependency.repo_url)
            repository = r"(?!\.{1,2}$)[A-Za-z0-9_.-]+" if kind == "mod" else r"[A-Za-z0-9_-]+"
            if url.scheme != "https" or url.netloc != "github.com" or not re.fullmatch(r"/[A-Za-z0-9_-]+/" + repository, url.path) or url.query or url.fragment:
                raise ValueError("Plugin dependencies must reference a GitHub repository")
            key = kind, dependency.repo_url.lower()
            if key in repos:
                raise ValueError("Duplicate plugin dependency")
            repos.add(key)
            parse_version_requirement(dependency.version)

    @staticmethod
    def from_dict(value: JsonValue) -> PluginInfo:
        data = json_object(value)
        required = {"name", "description", "authors"}
        if not required <= set(data) or not set(data) <= required | {"$schema", "mod_dependencies", "plugin_dependencies", "icon_url", "image_urls", "repo_url", "target"}:
            raise ValueError("Invalid plugin.json fields")
        if "$schema" in data:
            json_string(data["$schema"])
        info = PluginInfo(json_string(data["name"]), json_string(data["description"]), string_array(data["authors"]),
                          dependencies_from_dict(data, "plugin_dependencies"),
                          optional_string(data.get("icon_url")), string_array(data.get("image_urls", [])),
                          dependencies_from_dict(data, "mod_dependencies"),
                          optional_string(data.get("repo_url")),
                          PluginTarget(json_string(data.get("target", "shared"))))
        info.validate()
        return info

    def asdict(self) -> JsonObject:
        data: JsonObject = {"name": self.name, "description": self.description,
                            "authors": [author for author in self.authors],
                            "plugin_dependencies": [dep.asdict() for dep in self.plugin_dependencies],
                            "mod_dependencies": [dep.asdict() for dep in self.mod_dependencies],
                            "target": self.target.value}
        if self.icon_url is not None:
            data["icon_url"] = self.icon_url
        if self.image_urls:
            data["image_urls"] = [url for url in self.image_urls]
        if self.repo_url is not None:
            data["repo_url"] = self.repo_url
        return data


@dataclass(frozen=True)
class DllRelease:
    organization: str
    name: str
    version: str
    download_url: str
    sha256: str
    size: int
    info: PluginInfo | None = None
    tag: str | None = None
    release_date: datetime | None = None
    release_notes_markdown: str | None = None
    dll_file_name: str | None = None

    def validate(self) -> None:
        if self.info is not None:
            self.info.validate()
        for value in (self.organization, self.name):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError("Invalid DLL organization/name")
        Version.parse(self.version)
        if self.tag is not None and str(Version.parse(self.tag.removeprefix("v"))) != self.version:
            raise ValueError("DLL tag/version mismatch")
        if self.info is not None and self.info.repo_url is not None and self.info.repo_url.lower() != f"https://github.com/{self.organization}/{self.name}".lower():
            raise ValueError("DLL metadata repository mismatch")
        url = urlparse(self.download_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or not url.path.lower().endswith(".dll") or url.fragment:
            raise ValueError("DLL source must be an HTTPS DLL URL")
        if not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise ValueError("Invalid DLL SHA-256")
        if isinstance(self.size, bool) or self.size <= 0:
            raise ValueError("Invalid DLL size")
        if self.dll_file_name is not None and (not self.dll_file_name.lower().endswith(".dll") or "/" in self.dll_file_name or "\\" in self.dll_file_name):
            raise ValueError("Invalid DLL asset filename")

    @property
    def key(self) -> Tuple[str, str, str]:
        return self.organization.lower(), self.name.lower(), self.version.lower()

    @staticmethod
    def from_dict(value: JsonValue) -> DllRelease:
        data = json_object(value)
        fields = {"organization", "name", "version", "download_url", "sha256", "size"}
        optional = {"info", "tag", "release_date", "release_notes_markdown", "dll_file_name"}
        if not fields <= set(data) or not set(data) <= fields | optional:
            raise ValueError("Invalid DLL metadata fields")
        release = DllRelease(json_string(data["organization"]), json_string(data["name"]),
                             json_string(data["version"]), json_string(data["download_url"]),
                              json_string(data["sha256"]), json_int(data["size"]),
                              PluginInfo.from_dict(data["info"]) if "info" in data else None,
                              optional_string(data.get("tag")),
                              datetime.fromisoformat(json_string(data["release_date"])) if data.get("release_date") is not None else None,
                              optional_string(data.get("release_notes_markdown")), optional_string(data.get("dll_file_name")))
        release.validate()
        return release

    def asdict(self) -> JsonObject:
        data: JsonObject = {"organization": self.organization, "name": self.name, "version": self.version,
                            "download_url": self.download_url, "sha256": self.sha256, "size": self.size}
        if self.info is not None:
            data["info"] = self.info.asdict()
        if self.tag is not None:
            data["tag"] = self.tag
        if self.release_date is not None:
            data["release_date"] = self.release_date.isoformat()
        if self.release_notes_markdown is not None:
            data["release_notes_markdown"] = self.release_notes_markdown
        if self.dll_file_name is not None:
            data["dll_file_name"] = self.dll_file_name
        return data

    def package_dict(self) -> JsonObject:
        return {"tag": self.tag or self.version, "hash": self.sha256, "dll_file_name": self.dll_file_name,
                "download_url": self.download_url, "size": self.size,
                "release_date": self.release_date.isoformat() if self.release_date is not None else None,
                "info": self.info.asdict() if self.info is not None else None,
                "release_notes_markdown": self.release_notes_markdown}

    @staticmethod
    def from_package_dict(org: str, name: str, value: JsonValue) -> DllRelease:
        data = json_object(value)
        if set(data) != {"tag", "hash", "dll_file_name", "download_url", "size", "release_date", "info", "release_notes_markdown"}:
            raise ValueError("Invalid plugin release fields")
        tag = json_string(data["tag"])
        release = DllRelease(org, name, str(Version.parse(tag.removeprefix("v"))), json_string(data["download_url"]),
                             json_string(data["hash"]), json_int(data["size"]),
                             PluginInfo.from_dict(data["info"]) if data["info"] is not None else None,
                             tag, datetime.fromisoformat(json_string(data["release_date"])) if data["release_date"] is not None else None,
                             optional_string(data["release_notes_markdown"]), optional_string(data["dll_file_name"]))
        release.validate()
        return release


@dataclass(frozen=True)
class Plugin:
    releases: List[DllRelease]

    def sorted_releases(self) -> List[DllRelease]:
        def date(release: DllRelease) -> float:
            return release.release_date.timestamp() if release.release_date is not None else float("-inf")
        return sorted(self.releases, key=date, reverse=True)

    def asdict(self) -> JsonObject:
        releases = self.sorted_releases()
        info = self.latest_info()
        return {"latest_release_info": info.asdict(), "releases": [release.package_dict() for release in releases]}

    def latest_info(self) -> PluginInfo:
        info = next((release.info for release in self.sorted_releases() if release.info is not None), None)
        if info is None:
            raise ValueError("Plugin package has no metadata")
        return info

    @staticmethod
    def from_dict(org: str, name: str, value: JsonValue) -> Plugin:
        data = json_object(value)
        if set(data) != {"latest_release_info", "releases"}:
            raise ValueError("Invalid plugin package fields")
        latest = PluginInfo.from_dict(data["latest_release_info"])
        releases = [DllRelease.from_package_dict(org, name, item) for item in json_array(data["releases"])]
        plugin = Plugin(releases)
        if not releases or latest != plugin.latest_info():
            raise ValueError("Plugin latest-release metadata mismatch")
        return plugin


def validate_dll_entries(value: JsonValue) -> List[DllRelease]:
    releases = [DllRelease.from_dict(entry) for entry in json_array(value)]
    validate_dll_releases(releases)
    return releases


def validate_dll_releases(releases: List[DllRelease]) -> None:
    for release in releases:
        release.validate()
    keys = [release.key for release in releases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate DLL release")
    for release in releases:
        if release.info is None:
            continue  # Previously approved entries predate plugin.json.
        for dependency in release.info.plugin_dependencies:
            org, name = urlparse(dependency.repo_url).path.strip("/").split("/")
            if org.lower() == release.key[0] and name.lower() == release.key[1]:
                raise ValueError("Plugin cannot depend on itself")
            if not any(candidate.key[0] == org.lower() and candidate.key[1] == name.lower() and dependency_matches(candidate.version, dependency.version)
                       for candidate in releases):
                raise ValueError(f"Unregistered plugin dependency: {dependency.repo_url} {dependency.version}")
