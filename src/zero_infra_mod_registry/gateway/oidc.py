"""Verify GitHub OIDC signatures and authorize tag workflows."""
from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
import re
from threading import Lock
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from zero_infra_mod_registry.gateway.models import Config, GatewayError, Identity, repository_name
from zero_infra_mod_registry.gateway.transport import Transport
from zero_infra_mod_registry.utils.json_types import JsonObject, decode_json, json_array, json_int, json_object, json_string

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks"


def unbase64(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Verifier:
    def __init__(self, config: Config, transport: Transport, clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.transport = transport
        self.clock = clock
        self.keys: dict[str, rsa.RSAPublicKey] = {}
        self.last_refresh = float("-inf")
        self.lock = Lock()

    def _key(self, kid: str) -> rsa.RSAPublicKey:
        with self.lock:
            now = self.clock()
            if now - self.last_refresh > 3600 or (kid not in self.keys and now - self.last_refresh > 60):
                document = json_object(self.transport.request("GET", JWKS_URL))
                keys: dict[str, rsa.RSAPublicKey] = {}
                for value in json_array(document.get("keys")):
                    key = json_object(value)
                    if key.get("kty") != "RSA" or key.get("use", "sig") != "sig" or key.get("alg", "RS256") != "RS256":
                        continue
                    n = int.from_bytes(unbase64(json_string(key.get("n"))), "big")
                    e = int.from_bytes(unbase64(json_string(key.get("e"))), "big")
                    if n.bit_length() < 2048:
                        raise ValueError("OIDC signing key is too small")
                    keys[json_string(key.get("kid"))] = rsa.RSAPublicNumbers(e, n).public_key()
                self.keys = keys
                self.last_refresh = now
            if kid not in self.keys:
                raise ValueError("Unknown signing key")
            return self.keys[kid]

    def verify(self, token: str) -> Identity:
        try:
            if len(token) > 16384:
                raise ValueError("Token too large")
            header_part, payload_part, signature_part = token.split(".")
            header = json_object(decode_json(unbase64(header_part).decode("utf-8")))
            if header.get("alg") != "RS256" or "crit" in header:
                raise ValueError("Unsupported token algorithm")
            key = self._key(json_string(header.get("kid")))
            key.verify(unbase64(signature_part), f"{header_part}.{payload_part}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
            claims = json_object(decode_json(unbase64(payload_part).decode("utf-8")))
            return self._identity(claims)
        except (ValueError, KeyError, UnicodeError, binascii.Error, InvalidSignature) as error:
            raise GatewayError(401, "Invalid or unauthorized GitHub OIDC token") from error

    def _identity(self, claims: JsonObject) -> Identity:
        now = self.clock()
        if claims.get("iss") != ISSUER or claims.get("aud") != self.config.audience:
            raise ValueError("Wrong issuer or audience")
        issued = json_int(claims.get("iat"))
        expires = json_int(claims.get("exp"))
        if expires <= now or json_int(claims.get("nbf")) > now + 30 or issued > now + 30 or expires <= issued or expires - issued > 900 or now - issued > 900:
            raise ValueError("Invalid token validity window")
        if claims.get("event_name") not in {"push", "release", "workflow_dispatch"} or claims.get("ref_type") != "tag" or claims.get("repository_visibility") != "public":
            raise ValueError("Only public tag workflows are accepted")
        ref = json_string(claims.get("ref"))
        if not ref.startswith("refs/tags/"):
            raise ValueError("Tag reference required")
        repository_id = json_string(claims.get("repository_id"))
        owner_id = json_string(claims.get("repository_owner_id"))
        sha = json_string(claims.get("sha"))
        token_id = json_string(claims.get("jti"))
        if not repository_id.isdecimal() or not owner_id.isdecimal() or not re.fullmatch(r"[0-9a-f]{40}", sha) or not token_id or len(token_id) > 200:
            raise ValueError("Invalid repository identity")
        if self.config.allowed_repository_ids and repository_id not in self.config.allowed_repository_ids:
            raise ValueError("Repository is not enrolled")
        return Identity(repository_name(json_string(claims.get("repository"))), repository_id, owner_id, ref.removeprefix("refs/tags/"), sha, token_id)
