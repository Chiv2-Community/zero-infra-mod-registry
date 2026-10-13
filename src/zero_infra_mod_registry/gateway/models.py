"""Validated configuration and request models."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import semver

from zero_infra_mod_registry.utils.json_types import JsonObject, json_string


class GatewayError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def repository_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repository must be owner/name")
    if any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("Invalid repository name")
    return value


@dataclass(frozen=True)
class Config:
    audience: str
    registry: str
    app_id: str
    installation_id: str
    private_key_file: Path
    state_directory: Path
    public_read_token: str = ""
    allowed_repository_ids: frozenset[str] = frozenset()
    requests_per_hour: int = 20
    global_requests_per_hour: int = 10
    host: str = "0.0.0.0"
    port: int = 8080

    def __post_init__(self) -> None:
        parsed = urlsplit(self.audience)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/registrations":
            raise ValueError("GATEWAY_AUDIENCE must be a public HTTPS URL ending in /registrations")
        repository_name(self.registry)
        if not self.app_id.isdecimal() or not self.installation_id.isdecimal():
            raise ValueError("GitHub App and installation IDs must be numeric")
        if self.requests_per_hour < 1 or self.global_requests_per_hour < 1 or not 1 <= self.port <= 65535:
            raise ValueError("Rate limits and port must be positive")
        if any(not value.isdecimal() for value in self.allowed_repository_ids):
            raise ValueError("Allowed repository IDs must be numeric")

    @classmethod
    def from_environment(cls) -> Config:
        return cls(
            audience=os.environ["GATEWAY_AUDIENCE"],
            registry=os.environ["REGISTRY_REPOSITORY"],
            app_id=os.environ["GITHUB_APP_ID"],
            installation_id=os.environ["GITHUB_INSTALLATION_ID"],
            private_key_file=Path(os.environ["GITHUB_PRIVATE_KEY_FILE"]),
            state_directory=Path(os.environ.get("GATEWAY_STATE_DIRECTORY", "/data")),
            public_read_token=os.environ.get("GITHUB_PUBLIC_READ_TOKEN", ""),
            allowed_repository_ids=frozenset(value.strip() for value in os.environ.get("ALLOWED_REPOSITORY_IDS", "").split(",") if value.strip()),
            requests_per_hour=int(os.environ.get("REQUESTS_PER_HOUR", "20")),
            global_requests_per_hour=int(os.environ.get("GLOBAL_REQUESTS_PER_HOUR", "10")),
            host=os.environ.get("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.environ.get("GATEWAY_PORT", "8080")),
        )


@dataclass(frozen=True)
class Identity:
    repository: str
    repository_id: str
    owner_id: str
    tag: str
    sha: str
    token_id: str


@dataclass(frozen=True)
class Registration:
    kind: str
    tag: str
    asset: str

    @classmethod
    def from_json(cls, value: JsonObject) -> Registration:
        if set(value) - {"kind", "release_tag", "asset_name"}:
            raise ValueError("Only kind, release_tag and asset_name are accepted")
        kind = json_string(value.get("kind"))
        tag = json_string(value.get("release_tag"))
        asset = json_string(value.get("asset_name", ""))
        if kind not in {"plugin", "mod"}:
            raise ValueError("kind must be plugin or mod")
        if len(tag) > 200 or not semver.Version.is_valid(tag.removeprefix("v")):
            raise ValueError("release_tag must be a semantic version tag")
        suffix = ".dll" if kind == "plugin" else ".pak"
        if asset and (len(asset) > 255 or "/" in asset or "\\" in asset or any(ord(c) < 32 for c in asset) or not asset.lower().endswith(suffix)):
            raise ValueError("asset_name must be an exact DLL or pak filename")
        return cls(kind, tag, asset)


@dataclass(frozen=True)
class Issue:
    url: str

    def as_json(self) -> JsonObject:
        return {"issue_url": self.url}
