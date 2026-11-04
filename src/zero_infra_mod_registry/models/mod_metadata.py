"""Generated metadata types and repository identity helpers."""
from dataclasses import dataclass
from typing import override

from generated_models.json_types import JsonObject, json_array
from generated_models.dependencies import Dependency
from generated_models.loading import merge_modinfo_dependencies


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
    from zero_infra_mod_registry.models.loading import load

    return [load(item, Dependency) for item in json_array(data.get(field_name, []))]


def mod_dependencies_from_dict(data: JsonObject) -> list[Dependency]:
    """Load dependency values and apply the generated compatibility transform."""
    return merge_modinfo_dependencies(dependencies_from_dict(data, "mod_dependencies"),
                                     dependencies_from_dict(data, "dependencies"))
