"""Bundle authoritative schemas into wheels and source distributions."""
from pathlib import Path
from typing import override

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SchemaBuildHook(BuildHookInterface[BuilderConfig]):
    @override
    def initialize(self, version: str, build_data: dict[str, str | bool | list[str] | dict[str, str]]) -> None:
        root = Path(self.root)
        schemas = root / "schemas"
        if not schemas.is_dir():
            schemas = root.parents[1] / "schemas"
        if not schemas.is_dir():
            raise FileNotFoundError("Missing schemas directory")
        includes = build_data.setdefault("force_include", {})
        if not isinstance(includes, dict):
            raise TypeError("force_include must be a path mapping")
        destination = "generated_models/schemas" if self.target_name == "wheel" else "schemas"
        includes[str(schemas)] = destination
