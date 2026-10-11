"""Validated DLL metadata, independent of pak mod metadata."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Tuple
from urllib.parse import urlparse
from semver import Version
from zero_infra_mod_registry.models.mod_metadata import Dependency

from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, json_array, json_int, json_object, json_string, string_array


def dependency_matches(version: str, requirement: str) -> bool:
    candidate = Version.parse(version)
    requirement = requirement.removeprefix("v")
    if requirement.startswith("^"):
        base = Version.parse(requirement[1:])
        upper = Version(base.major + 1, 0, 0) if base.major else (
            Version(0, base.minor + 1, 0) if base.minor else Version(0, 0, base.patch + 1))
        return base <= candidate < upper
    return all([candidate.match(part.strip()) for part in requirement.split(",")])


@dataclass(frozen=True)
class PluginInfo:
    name: str
    description: str
    authors: List[str]
    dependencies: List[Dependency]

    def validate(self) -> None:
        if not self.name.strip() or not self.description.strip() or not self.authors or any(not author.strip() for author in self.authors):
            raise ValueError("plugin.json requires a name, description and authors")
        repos: set[str] = set()
        for dependency in self.dependencies:
            url = urlparse(dependency.repo_url)
            if url.scheme != "https" or url.netloc != "github.com" or not re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", url.path) or url.query or url.fragment:
                raise ValueError("Plugin dependencies must reference a GitHub repository")
            key = dependency.repo_url.lower()
            if key in repos:
                raise ValueError("Duplicate plugin dependency")
            repos.add(key)
            dependency_matches("1.0.0", dependency.version)

    @staticmethod
    def from_dict(value: JsonValue) -> PluginInfo:
        data = json_object(value)
        if set(data) != {"name", "description", "authors", "dependencies"}:
            raise ValueError("Invalid plugin.json fields")
        info = PluginInfo(json_string(data["name"]), json_string(data["description"]), string_array(data["authors"]),
                          [Dependency.from_dict(item) for item in json_array(data["dependencies"])])
        info.validate()
        return info

    def asdict(self) -> JsonObject:
        return {"name": self.name, "description": self.description,
                "authors": [author for author in self.authors], "dependencies": [dep.asdict() for dep in self.dependencies]}


@dataclass(frozen=True)
class DllRelease:
    organization: str
    name: str
    version: str
    download_url: str
    sha256: str
    size: int
    info: PluginInfo | None = None

    def validate(self) -> None:
        if self.info is not None:
            self.info.validate()
        for value in (self.organization, self.name):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError("Invalid DLL organization/name")
        Version.parse(self.version)
        url = urlparse(self.download_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or not url.path.lower().endswith(".dll") or url.fragment:
            raise ValueError("DLL source must be an HTTPS DLL URL")
        if not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise ValueError("Invalid DLL SHA-256")
        if isinstance(self.size, bool) or self.size <= 0:
            raise ValueError("Invalid DLL size")

    @property
    def key(self) -> Tuple[str, str, str]:
        return self.organization.lower(), self.name.lower(), self.version.lower()

    @staticmethod
    def from_dict(value: JsonValue) -> DllRelease:
        data = json_object(value)
        fields = {"organization", "name", "version", "download_url", "sha256", "size"}
        if set(data) not in (fields, fields | {"info"}):
            raise ValueError("Invalid DLL metadata fields")
        release = DllRelease(json_string(data["organization"]), json_string(data["name"]),
                             json_string(data["version"]), json_string(data["download_url"]),
                              json_string(data["sha256"]), json_int(data["size"]),
                              PluginInfo.from_dict(data["info"]) if "info" in data else None)
        release.validate()
        return release

    def asdict(self) -> JsonObject:
        data: JsonObject = {"organization": self.organization, "name": self.name, "version": self.version,
                            "download_url": self.download_url, "sha256": self.sha256, "size": self.size}
        if self.info is not None:
            data["info"] = self.info.asdict()
        return data


def validate_dll_entries(value: JsonValue) -> List[DllRelease]:
    releases = [DllRelease.from_dict(entry) for entry in json_array(value)]
    keys = [release.key for release in releases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate DLL release")
    for release in releases:
        if release.info is None:
            continue  # Previously approved entries predate plugin.json.
        for dependency in release.info.dependencies:
            org, name = urlparse(dependency.repo_url).path.strip("/").split("/")
            if org.lower() == release.key[0] and name.lower() == release.key[1]:
                raise ValueError("Plugin cannot depend on itself")
            if not any(candidate.key[0] == org.lower() and candidate.key[1] == name.lower() and dependency_matches(candidate.version, dependency.version)
                       for candidate in releases):
                raise ValueError(f"Unregistered plugin dependency: {dependency.repo_url} {dependency.version}")
    return releases
