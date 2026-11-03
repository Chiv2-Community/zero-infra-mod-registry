"""Bundle the authoritative request schema without a source-tree copy."""
from pathlib import Path
from typing import override

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SchemaBuildHook(BuildHookInterface[BuilderConfig]):
    @override
    def initialize(self, version: str, build_data: dict[str, str | bool | list[str] | dict[str, str]]) -> None:
        root = Path(self.root)
        # Sdists carry the same schema under their own root for isolated builds.
        schema = root / "schemas/request.schema.json"
        if not schema.is_file():
            schema = root.parents[1] / "schemas/request.schema.json"
        if not schema.is_file():
            raise FileNotFoundError("Missing schemas/request.schema.json")
        includes = build_data.setdefault("force_include", {})
        if not isinstance(includes, dict):
            raise TypeError("force_include must be a path mapping")
        destination = "mod_registry_core/schemas/request.schema.json" if self.target_name == "wheel" else "schemas/request.schema.json"
        includes[str(schema)] = destination
