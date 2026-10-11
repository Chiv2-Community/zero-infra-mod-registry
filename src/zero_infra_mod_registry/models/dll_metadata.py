"""Validated DLL metadata, independent of pak mod metadata."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Tuple
from urllib.parse import urlparse
from semver import Version

from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, json_array, json_int, json_object, json_string


@dataclass(frozen=True)
class DllRelease:
    organization: str
    name: str
    version: str
    download_url: str
    sha256: str
    size: int

    def validate(self) -> None:
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
        if set(data) != {"organization", "name", "version", "download_url", "sha256", "size"}:
            raise ValueError("Invalid DLL metadata fields")
        release = DllRelease(json_string(data["organization"]), json_string(data["name"]),
                             json_string(data["version"]), json_string(data["download_url"]),
                             json_string(data["sha256"]), json_int(data["size"]))
        release.validate()
        return release

    def asdict(self) -> JsonObject:
        return {"organization": self.organization, "name": self.name, "version": self.version,
                "download_url": self.download_url, "sha256": self.sha256, "size": self.size}


def validate_dll_entries(value: JsonValue) -> List[DllRelease]:
    releases = [DllRelease.from_dict(entry) for entry in json_array(value)]
    keys = [release.key for release in releases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate DLL release")
    return releases
