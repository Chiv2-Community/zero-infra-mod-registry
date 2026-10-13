"""Pure release-selection and registration wire-contract helpers."""
from collections.abc import Iterable
import re

from mod_registry_core.json_types import JsonObject, decode_json, json_object, json_string


def selected_dll_name(names: Iterable[str], dll_file: str | None = None) -> str:
    """Select by filename before checking upload eligibility or downloading."""
    dlls = [name for name in names if name.lower().endswith(".dll")]
    if dll_file is not None:
        dlls = [name for name in dlls if name == dll_file]
        if len(dlls) != 1:
            raise ValueError(f"Requested DLL asset must match exactly one DLL: {dll_file!r}")
    if not dlls:
        raise ValueError("The release contains no DLL assets")
    if len(dlls) != 1:
        raise ValueError("A DLL release must contain exactly one DLL asset unless --dll-file selects one")
    return dlls[0]


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
    # Keep identical to issue.cjs: ASCII fence spacing and LF/CRLF boundaries.
    # Unicode whitespace and multiline anchors differ between Python and JS.
    block = re.search(r"(?:^|\n)```(?:json)?[ \t\r]*\n([\s\S]*?)\n```[ \t\r]*(?=\n|(?![\s\S]))", body)
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
