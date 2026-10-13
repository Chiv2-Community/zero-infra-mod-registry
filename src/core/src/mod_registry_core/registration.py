"""Pure release-selection and registration wire-contract helpers."""
from collections.abc import Iterable
import re

from mod_registry_core.json_types import JsonObject, decode_json, json_object, json_string


def single_pak_name(names: Iterable[str], tag: str) -> str:
    """Preserve the registry's case-sensitive, exactly-one-PAK contract."""
    paks = [name for name in names if name.endswith(".pak")]
    if not paks:
        raise ValueError(f"No pak file found for release {tag}.")
    if len(paks) > 1:
        raise ValueError(f"Multiple pak files found for release {tag}.")
    return paks[0]


def registration_payload(kind: str, repository: str, tag: str, asset: str) -> JsonObject:
    payload: JsonObject = {
        "action": "add-dll-release" if kind == "plugin" else "add-package-release",
        "repo_url": f"https://github.com/{repository}",
        "release_tag": tag,
    }
    if kind == "plugin" and asset:
        payload["dll_file"] = asset
    return payload


def parse_registration_payload(body: str) -> JsonObject:
    """Read the same first fenced request consumed by the issue workflow."""
    block = re.search(r"^```(?:json)?\s*\n([\s\S]*?)^```\s*$", body, re.MULTILINE)
    if block is None:
        raise ValueError("Include a fenced JSON registration request")
    value = json_object(decode_json(block[1]))
    action = json_string(value.get("action"))
    if action not in {"add-package-release", "add-dll-release"}:
        raise ValueError("Invalid registration action")
    payload: JsonObject = {"action": action}
    for field in ("repo_url", "release_tag", "dll_file"):
        if field == "dll_file" and field not in value:
            continue
        text = json_string(value.get(field))
        if not text.strip():
            raise ValueError(f"{field} must be a nonempty string")
        payload[field] = text
    return payload
