"""Read YAML schema/spec documents; model payloads remain JSON."""
from pathlib import Path
from typing import cast

import yaml

from generated_models.json_types import JsonObject, JsonValue, json_object


def read_document(path: Path) -> JsonObject:
    return json_object(cast(JsonValue, yaml.safe_load(path.read_text())))
