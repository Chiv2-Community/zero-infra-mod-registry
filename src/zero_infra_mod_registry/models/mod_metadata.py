"""Generated metadata types and repository identity helpers."""
from dataclasses import dataclass
from typing import override

from mod_registry_core.json_types import JsonObject, json_array
from zero_infra_mod_registry.models.generated_dependencies import Dependency as Dependency
from zero_infra_mod_registry.models.generated import (
    Mod as Mod, ModInfo as ModInfo, Release as Release,
)


@dataclass(frozen=True)
class Repo:
    """Internal repository identity, not a metadata document."""

    org: str
    name: str

    @override
    def __str__(self) -> str:
        return f"{self.org}/{self.name}"

    def github_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


def dependencies_from_dict(data: JsonObject, field_name: str) -> list[Dependency]:
    return [Dependency.from_dict(item) for item in json_array(data.get(field_name, []))]


def mod_dependencies_from_dict(data: JsonObject) -> list[Dependency]:
    """Merge both schema-declared spellings outside the generated model."""
    dependencies = dependencies_from_dict(data, "mod_dependencies") + dependencies_from_dict(data, "dependencies")
    unique: dict[tuple[str, str], Dependency] = {}
    for dependency in dependencies:
        unique[(dependency.repo_url.lower(), dependency.version)] = dependency
    return list(unique.values())
