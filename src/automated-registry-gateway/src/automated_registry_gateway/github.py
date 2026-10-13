"""GitHub App credentials and registration issue creation."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from threading import Lock
import time
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from automated_registry_gateway.models import Config, GatewayError, Identity, Issue, Registration
from automated_registry_gateway.oidc import base64url
from automated_registry_gateway.transport import Transport
from mod_registry_core.json_types import JsonObject, json_array, json_bool, json_int, json_object, json_string
from mod_registry_core.registration import parse_registration_payload, registration_payload, single_pak_name

API = "https://api.github.com"


class GithubApp:
    def __init__(self, config: Config, transport: Transport, clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.transport = transport
        self.clock = clock
        key = serialization.load_pem_private_key(config.private_key_file.read_bytes(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("GitHub App key must be an RSA private key of at least 2048 bits")
        self.key = key
        self.token = ""
        self.expires = 0.0
        self.lock = Lock()

    def _jwt(self) -> str:
        now = int(self.clock())
        header = base64url(b'{"alg":"RS256","typ":"JWT"}')
        claims: JsonObject = {"iat": now - 60, "exp": now + 540, "iss": self.config.app_id}
        payload = base64url(json.dumps(claims).encode())
        message = f"{header}.{payload}"
        signature = self.key.sign(message.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{message}.{base64url(signature)}"

    def installation_token(self) -> str:
        with self.lock:
            if self.expires > self.clock() + 60:
                return self.token
            app_jwt = self._jwt()
            installation = json_object(self.transport.request("GET", f"{API}/app/installations/{self.config.installation_id}", app_jwt))
            account = json_object(installation.get("account"))
            if json_string(account.get("login")).lower() != self.config.registry.split("/")[0].lower():
                raise GatewayError(503, "GitHub App installation does not match the registry owner")
            permissions: JsonObject = {"issues": "write"}
            request: JsonObject = {"repositories": [self.config.registry.split("/")[1]], "permissions": permissions}
            data = json_object(self.transport.request("POST", f"{API}/app/installations/{self.config.installation_id}/access_tokens", app_jwt, request))
            self.token = json_string(data.get("token"))
            self.expires = datetime.fromisoformat(json_string(data.get("expires_at")).replace("Z", "+00:00")).timestamp()
            return self.token

    def verify_release(self, identity: Identity, request: Registration) -> None:
        path = f"{API}/repos/{identity.repository}"
        repo = json_object(self.transport.request("GET", path, self.config.public_read_token))
        owner = json_object(repo.get("owner"))
        if str(json_int(repo.get("id"))) != identity.repository_id or str(json_int(owner.get("id"))) != identity.owner_id or json_bool(repo.get("private")):
            raise GatewayError(403, "Published repository identity does not match the workflow")
        tag_ref = quote(f"refs/tags/{request.tag}", safe="")
        commit = json_object(self.transport.request("GET", f"{path}/commits/{tag_ref}", self.config.public_read_token))
        if commit.get("sha") != identity.sha:
            raise GatewayError(403, "Release tag no longer points to the workflow commit")
        release = json_object(self.transport.request("GET", f"{path}/releases/tags/{quote(request.tag, safe='')}", self.config.public_read_token))
        if json_bool(release.get("draft")) or release.get("tag_name") != request.tag:
            raise GatewayError(422, "Release must be published with the requested tag")
        suffix = ".dll" if request.kind == "plugin" else ".pak"
        release_assets = [json_object(value) for value in json_array(release.get("assets"))]
        if request.kind == "mod":
            try:
                single_pak_name((json_string(asset.get("name")) for asset in release_assets), request.tag)
            except ValueError as error:
                raise GatewayError(422, str(error)) from error
        assets: list[str] = []
        for asset in release_assets:
            name = json_string(asset.get("name"))
            matches = name.lower().endswith(suffix) if request.kind == "plugin" else name.endswith(suffix)
            if matches and asset.get("state") == "uploaded" and json_int(asset.get("size")) > 0:
                assets.append(name)
        if request.asset:
            valid = request.asset in assets
        else:
            valid = len(assets) == 1
        if not valid:
            raise GatewayError(422, "Select an uploaded, nonempty release asset; multiple DLLs require asset_name")

    def create_issue(self, identity: Identity, request: Registration) -> Issue:
        token = self.installation_token()
        marker = f"<!-- c2modregistry:{identity.repository}:{request.tag} -->"
        payload = registration_payload(request.kind, identity.repository, request.tag, request.asset)
        path = f"{API}/repos/{self.config.registry}/issues"
        # Recover after a process crash between GitHub creation and local commit.
        # GitHub timestamps order pages consistently for an unchanged issue list.
        for page in range(1, 101):
            issues = json_array(self.transport.request("GET", f"{path}?state=all&sort=created&direction=desc&per_page=100&page={page}", token))
            for value in issues:
                issue = json_object(value)
                if "pull_request" not in issue and marker in json_string(issue.get("body") or ""):
                    try:
                        recovered = parse_registration_payload(json_string(issue.get("body")))
                    except ValueError as error:
                        raise GatewayError(409, "Existing registry issue has an invalid registration payload; edit its registry issue") from error
                    if recovered != payload:
                        raise GatewayError(409, "This tag already has a different request; edit its registry issue")
                    return Issue(json_string(issue.get("html_url")))
            if len(issues) < 100:
                break
        else:
            raise GatewayError(503, "Registry issue history is too large for safe duplicate detection")
        body = f"{marker}\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"
        kind = "DLL" if request.kind == "plugin" else "PAK"
        result = json_object(self.transport.request("POST", path, token, {
            "title": f"[{kind} RELEASE] {identity.repository.split('/')[1]} Version {request.tag}",
            "body": body,
        }))
        return Issue(json_string(result.get("html_url")))
