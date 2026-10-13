"""Typed test doubles for external APIs; no dynamically typed mock attributes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Generic, Iterator, TypeVar, cast, override

import requests
from github import Github
from github.GitRelease import GitRelease
from github.GitReleaseAsset import GitReleaseAsset
from github.PaginatedList import PaginatedList
from urllib3.response import HTTPResponse

from zero_infra_mod_registry.models import DllRelease, Mod, ModInfo, Release, Repo
from zero_infra_mod_registry.models.pak_manifest import Manifest
from zero_infra_mod_registry.retriever import ModMetadataRetriever

T = TypeVar("T")


def mod_fixture(name: str = "Plugin", tag: str = "v1.0.0", date: datetime = datetime(2023, 1, 1)) -> Mod:
    info = ModInfo(f"https://github.com/Test/{name}", name, "Fixture", None, [], ["Author"], [])
    release = Release(tag, "a" * 128, f"{name}.pak", date, info, "Notes", Manifest([], [], [], [], []))
    return Mod(info, [release])


class FakeRetriever(ModMetadataRetriever):
    def __init__(self) -> None:
        self.releases: dict[tuple[str, str], Release] = {}
        self.dll: DllRelease | None = None
        self.dll_error: Exception | None = None
        self.dll_calls: list[tuple[Repo, str, str | None]] = []
        self.measurement = ("0" * 64, 1)
        self.release_calls: list[tuple[Repo, str]] = []

    @override
    def fetch_release_metadata(self, repo: Repo, release_tag: str) -> Release | None:
        self.release_calls.append((repo, release_tag))
        return self.releases.get((str(repo), release_tag))

    @override
    def update_mod_with_release(self, mod: Mod, release: Release) -> Mod:
        def date(item: Release) -> datetime:
            return item.release_date
        releases = sorted(mod.releases + [release], key=date, reverse=True)
        return Mod(releases[0].info, releases)

    @override
    def fetch_dll_release(self, repo: Repo, release_tag: str, dll_file: str | None = None) -> DllRelease:
        self.dll_calls.append((repo, release_tag, dll_file))
        if self.dll_error is not None:
            raise self.dll_error
        if self.dll is None:
            raise ValueError("No DLL fixture")
        return self.dll

    @override
    def measure_dll(self, url: str) -> tuple[str, int]:
        return self.measurement


@dataclass
class FakeAsset:
    name: str = "Plugin.dll"
    browser_download_url: str = "https://example.com/Plugin.dll"
    size: int = 20
    updated_at: datetime = datetime(2023, 1, 1)

    def as_asset(self) -> GitReleaseAsset:
        # A test-only nominal API boundary; every field consumed by production
        # is declared above and uses the same type as the PyGithub property.
        return cast(GitReleaseAsset, self)


@dataclass
class FakeRelease:
    tag_name: str = "v1.0.0"
    draft: bool = False
    body: str = "Release notes"
    assets: list[FakeAsset] = field(default_factory=list)
    published_at: datetime = datetime(2023, 1, 1)

    def get_assets(self) -> PaginatedList[GitReleaseAsset]:
        pages = FakePages([asset.as_asset() for asset in self.assets])
        return cast(PaginatedList[GitReleaseAsset], pages)

    def as_release(self) -> GitRelease:
        return cast(GitRelease, self)


@dataclass
class FakePages(Generic[T]):
    items: list[T]

    @property
    def totalCount(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)


class FakeRepository:
    def __init__(self, releases: list[FakeRelease]) -> None:
        self.releases = releases
        self.tag_calls: list[str] = []

    def get_release(self, tag: str) -> GitRelease:
        self.tag_calls.append(tag)
        return next(release.as_release() for release in self.releases if release.tag_name == tag)


class FakeGithub:
    def __init__(self, releases: list[FakeRelease]) -> None:
        self.repository = FakeRepository(releases)
        self.repo_calls: list[str] = []

    def get_repo(self, name: str) -> FakeRepository:
        self.repo_calls.append(name)
        return self.repository

    def as_github(self) -> Github:
        return cast(Github, self)


def response_fixture(data: bytes, url: str, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = data
    response.raw = HTTPResponse(body=BytesIO(data), status=status, preload_content=False)
    return response
