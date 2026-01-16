from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List

from zero_infra_mod_registry.models.manifest import Manifest


@dataclass(frozen=True)
class Repo:
    org: str
    name: str

    def __str__(self) -> str:
        return f"{self.org}/{self.name}"

    def github_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


@dataclass(frozen=True)
class Dependency:
    repo_url: str
    version: str

    @staticmethod
    def from_dict(data: Dict) -> "Dependency":
        return Dependency(repo_url=data["repo_url"], version=data["version"])


@dataclass(frozen=True)
class ModInfo:
    repo_url: str
    name: str
    description: str
    icon_url: str | None
    image_urls: List[str]
    authors: List[str]
    dependencies: List[Dependency]
    mod_type: str

    @staticmethod
    def from_dict(data: Dict) -> "ModInfo":
        return ModInfo(
            repo_url=data["repo_url"],
            name=data["name"],
            description=data["description"],
            icon_url=data.get("icon_url"),
            image_urls=data.get("image_urls", []),
            authors=data["authors"],
            dependencies=[Dependency.from_dict(dep) for dep in data["dependencies"]],
            mod_type=data.get("mod_type", "Shared"),
        )


@dataclass(frozen=True)
class Release:
    tag: str
    hash: str
    pak_file_name: str
    release_date: datetime
    info: ModInfo
    release_notes_markdown: str | None
    manifest: Manifest | None = None

    @staticmethod
    def from_dict(data: Dict) -> "Release":
        manifest = Manifest.from_dict(data["manifest"]) if "manifest" in data else None
        return Release(
            tag=data["tag"],
            hash=data["hash"],
            pak_file_name=data["pak_file_name"],
            release_date=datetime.fromisoformat(data["release_date"]),
            info=ModInfo.from_dict(data["info"]),
            release_notes_markdown=data["release_notes_markdown"],
            manifest=manifest
        )


@dataclass(frozen=True)
class Mod:
    latest_release_info: ModInfo
    releases: List[Release]

    @staticmethod
    def from_dict(data: Dict) -> "Mod":
        return Mod(
            latest_release_info=ModInfo.from_dict(data["latest_release_info"]),
            releases=[Release.from_dict(release) for release in data["releases"]],
        )

    def asdict(self) -> Dict:
        return asdict(self)
