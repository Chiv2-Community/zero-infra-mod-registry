"""Bounded HTTP access to fixed GitHub endpoints."""
from __future__ import annotations

from typing import Protocol

import requests

from automated_registry_gateway.models import GatewayError
from mod_registry_core.json_types import JsonObject, JsonValue, decode_json


class Transport(Protocol):
    def request(self, method: str, url: str, token: str = "", payload: JsonObject | None = None) -> JsonValue: ...


class GithubTransport:
    def request(self, method: str, url: str, token: str = "", payload: JsonObject | None = None) -> JsonValue:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "zero-infra-registry-gateway"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with requests.request(method, url, headers=headers, json=payload, timeout=(5, 20), allow_redirects=False, stream=True) as response:
                if response.status_code == 404:
                    raise GatewayError(422, "Repository, tag or published release not found")
                if not 200 <= response.status_code < 300:
                    raise GatewayError(502, "GitHub API request failed")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 2_000_000:
                        raise GatewayError(502, "GitHub response exceeded the size limit")
                    chunks.append(chunk)
                return decode_json(b"".join(chunks).decode("utf-8"))
        except (requests.RequestException, UnicodeError, ValueError) as error:
            raise GatewayError(502, "GitHub response unavailable or invalid") from error
