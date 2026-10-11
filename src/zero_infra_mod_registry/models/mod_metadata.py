from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, override

from zero_infra_mod_registry.models.pak_manifest import Manifest
from zero_infra_mod_registry.utils.json_types import (
    JsonObject, JsonValue, json_array, json_object, json_string, optional_string, string_array,
)


@dataclass(frozen=True)
class Repo:
    org: str
    name: str

    @override
    def __str__(self) -> str:
        return f"{self.org}/{self.name}"

    def github_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


@dataclass(frozen=True)
class Dependency:
    repo_url: str
    version: str

    @staticmethod
    def from_dict(value: JsonValue) -> Dependency:
        data = json_object(value)
        return Dependency(json_string(data["repo_url"]), json_string(data["version"]))

    def asdict(self) -> JsonObject:
        return {"repo_url": self.repo_url, "version": self.version}


def mod_dependencies_from_dict(data: JsonObject) -> List[Dependency]:
    # Preserve legacy declarations even if both spellings appear in one record.
    dependencies = [Dependency.from_dict(item) for item in
                    json_array(data.get("mod_dependencies", [])) + json_array(data.get("dependencies", []))]
    unique: dict[tuple[str, str], Dependency] = {}
    for dependency in dependencies:
        unique[(dependency.repo_url.lower(), dependency.version)] = dependency
    return list(unique.values())


@dataclass(frozen=True)
class ModInfo:
    repo_url: str
    name: str
    description: str
    icon_url: str | None
    image_urls: List[str]
    authors: List[str]
    mod_dependencies: List[Dependency]
    plugin_dependencies: List[Dependency] = field(default_factory=list)

    @property
    def dependencies(self) -> List[Dependency]:
        """Legacy Python accessor; JSON output uses the explicit field names."""
        return self.mod_dependencies

    @staticmethod
    def from_dict(value: JsonValue) -> ModInfo:
        data = json_object(value)
        return ModInfo(
            repo_url=json_string(data["repo_url"]), name=json_string(data["name"]),
            description=json_string(data["description"]), icon_url=optional_string(data.get("icon_url")),
            image_urls=string_array(data.get("image_urls", [])), authors=string_array(data["authors"]),
            mod_dependencies=mod_dependencies_from_dict(data),
            plugin_dependencies=[Dependency.from_dict(item) for item in json_array(data.get("plugin_dependencies", []))],
        )

    def asdict(self) -> JsonObject:
        return {"repo_url": self.repo_url, "name": self.name, "description": self.description,
                "icon_url": self.icon_url, "image_urls": [url for url in self.image_urls],
                "authors": [author for author in self.authors], "mod_dependencies": [dep.asdict() for dep in self.mod_dependencies],
                "plugin_dependencies": [dep.asdict() for dep in self.plugin_dependencies]}


@dataclass(frozen=True)
class Release:
    tag: str
    hash: str
    pak_file_name: str
    release_date: datetime
    info: ModInfo
    release_notes_markdown: str | None
    manifest: Manifest

    @staticmethod
    def from_dict(value: JsonValue) -> Release:
        data = json_object(value)
        return Release(
            tag=json_string(data["tag"]), hash=json_string(data["hash"]),
            pak_file_name=json_string(data["pak_file_name"]),
            release_date=datetime.fromisoformat(json_string(data["release_date"])),
            info=ModInfo.from_dict(data["info"]),
            release_notes_markdown=optional_string(data["release_notes_markdown"]),
            manifest=Manifest.from_dict(data["manifest"]),
        )

    def asdict(self) -> JsonObject:
        return {"tag": self.tag, "hash": self.hash, "pak_file_name": self.pak_file_name,
                "release_date": self.release_date.isoformat(), "info": self.info.asdict(),
                "release_notes_markdown": self.release_notes_markdown, "manifest": self.manifest.asdict()}


@dataclass(frozen=True)
class Mod:
    latest_release_info: ModInfo
    releases: List[Release]

    @staticmethod
    def from_dict(value: JsonValue) -> Mod:
        data = json_object(value)
        return Mod(ModInfo.from_dict(data["latest_release_info"]),
                   [Release.from_dict(item) for item in json_array(data["releases"])])

    def asdict(self) -> JsonObject:
        return {"latest_release_info": self.latest_release_info.asdict(),
                "releases": [release.asdict() for release in self.releases]}
