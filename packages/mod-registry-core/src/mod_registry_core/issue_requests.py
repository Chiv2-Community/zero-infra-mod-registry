"""Registration payloads and fenced JSON transport for registry issues."""
import re

from generated_models.json_types import JsonObject
from generated_models.loading import loads, serialize
from generated_models.requests import Action, RegistrationRequest


def registration_payload(kind: str, repository: str, tag: str, asset: str) -> JsonObject:
    request = RegistrationRequest(
        action=Action.ADD_DLL_RELEASE if kind == "plugin" else Action.ADD_PACKAGE_RELEASE,
        repo_url=f"https://github.com/{repository}",
        release_tag=tag,
        dll_file=asset if kind == "plugin" and asset else None,
    )
    return serialize(request)


def parse_registration_payload(body: str) -> JsonObject:
    """Read the same first fenced request consumed by the issue workflow."""
    # Keep identical to issue.cjs: ASCII fence spacing and LF/CRLF boundaries.
    # Unicode whitespace and multiline anchors differ between Python and JS.
    block = re.search(r"(?:^|\n)```(?:json)?[ \t\r]*\n([\s\S]*?)\n```[ \t\r]*(?=\n|(?![\s\S]))", body)
    if block is None:
        raise ValueError("Include a fenced JSON registration request")
    return serialize(loads(block[1], RegistrationRequest))
