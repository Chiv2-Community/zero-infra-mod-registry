"""Gateway trust boundary, GitHub App, persistence and HTTP regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
from threading import Thread
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import pytest
import requests

from automated_registry_gateway.github import API, GithubApp
from automated_registry_gateway.models import Config, GatewayError, Identity, Registration
from automated_registry_gateway.oidc import ISSUER, JWKS_URL, Verifier, base64url, unbase64
from automated_registry_gateway.server import GatewayServer
from automated_registry_gateway.service import Service
from mod_registry_core.json_types import JsonObject, JsonValue, decode_json, json_object

NOW = 1800000000
REPO = "Publisher/Plugin"
SHA = "b" * 40
TAG = "v1.0.0"
BODY: JsonObject = {"kind": "plugin", "release_tag": TAG, "asset_name": "Plugin.dll"}


@dataclass
class Clock:
    now: float = NOW

    def __call__(self) -> float:
        return self.now


class FakeTransport:
    def __init__(self, signing_key: rsa.RSAPrivateKey, clock: Clock) -> None:
        numbers = signing_key.public_key().public_numbers()
        self.jwk: JsonObject = {"kty": "RSA", "alg": "RS256", "kid": "test-key", "use": "sig",
            "n": base64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": base64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"))}
        self.clock = clock
        self.calls: list[tuple[str, str, str, JsonObject | None]] = []
        self.issues: list[JsonObject] = []
        self.repo: JsonObject = {"id": 321, "owner": {"id": 42}, "private": False}
        self.commit: JsonObject = {"sha": SHA}
        self.release: JsonObject = {"draft": False, "tag_name": TAG,
            "assets": [{"name": "Plugin.dll", "state": "uploaded", "size": 123}]}
        self.account = "RegistryOrg"
        self.fail_creation = False

    def request(self, method: str, url: str, token: str = "", payload: JsonObject | None = None) -> JsonValue:
        self.calls.append((method, url, token, payload))
        if url == JWKS_URL:
            return {"keys": [self.jwk]}
        if url == f"{API}/repos/{REPO}":
            return self.repo
        if url == f"{API}/repos/{REPO}/commits/{quote(f'refs/tags/{TAG}', safe='')}":
            return self.commit
        if url == f"{API}/repos/{REPO}/releases/tags/{quote(TAG, safe='')}":
            return self.release
        if url == f"{API}/app/installations/123":
            return {"account": {"login": self.account}}
        if url == f"{API}/app/installations/123/access_tokens":
            return {"token": "app-installation-token", "expires_at": datetime.fromtimestamp(self.clock() + 3600, timezone.utc).isoformat()}
        if url.startswith(f"{API}/repos/RegistryOrg/Registry/issues?"):
            return [issue for issue in self.issues]
        if url == f"{API}/repos/RegistryOrg/Registry/issues" and method == "POST":
            if self.fail_creation:
                raise GatewayError(502, "GitHub API request failed")
            assert payload is not None and token == "app-installation-token"
            issue: JsonObject = {"html_url": f"https://github.com/RegistryOrg/Registry/issues/{len(self.issues) + 1}", "body": payload["body"]}
            self.issues.append(issue)
            return issue
        raise AssertionError(f"Unexpected request {method} {url}")


@dataclass
class Harness:
    config: Config
    clock: Clock
    key: rsa.RSAPrivateKey
    transport: FakeTransport
    verifier: Verifier
    app: GithubApp
    service: Service

    def token(self, changes: JsonObject | None = None, header_changes: JsonObject | None = None) -> str:
        claims: JsonObject = {
            "iss": ISSUER, "aud": self.config.audience, "iat": int(self.clock()),
            "nbf": int(self.clock()), "exp": int(self.clock()) + 300,
            "repository": REPO, "repository_id": "321", "repository_owner_id": "42",
            "repository_visibility": "public", "sha": SHA, "event_name": "push",
            "ref": f"refs/tags/{TAG}", "ref_type": "tag", "jti": "token-1",
        }
        claims.update(changes or {})
        header: JsonObject = {"alg": "RS256", "kid": "test-key"}
        header.update(header_changes or {})
        message = f"{base64url(json.dumps(header).encode())}.{base64url(json.dumps(claims).encode())}"
        signature = self.key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{message}.{base64url(signature)}"


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = tmp_path / "app.pem"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    config = Config("https://registry.example.com/registrations", "RegistryOrg/Registry", "456", "123", pem, tmp_path / "state")
    clock = Clock()
    transport = FakeTransport(key, clock)
    verifier = Verifier(config, transport, clock)
    app = GithubApp(config, transport, clock)
    return Harness(config, clock, key, transport, verifier, app, Service(config, verifier, app, clock))


def test_signed_public_tag_identity(harness: Harness) -> None:
    identity = harness.verifier.verify(harness.token())
    assert identity == Identity(REPO, "321", "42", TAG, SHA, "token-1")
    harness.verifier.verify(harness.token())
    assert sum(url == JWKS_URL for _, url, _, _ in harness.transport.calls) == 1


@pytest.mark.parametrize("changes", [
    {"iss": "https://attacker.example"}, {"aud": "other"}, {"exp": NOW},
    {"nbf": NOW + 60}, {"iat": NOW + 60}, {"iat": NOW - 1000},
    {"exp": NOW + 1000}, {"repository_id": 321}, {"repository_owner_id": "bad"},
    {"repository": "../Plugin"}, {"repository": "a/b/c"}, {"sha": "bad"},
    {"event_name": "pull_request"}, {"event_name": "pull_request_target"},
    {"ref": "refs/heads/main"}, {"ref_type": "branch"},
    {"repository_visibility": "private"}, {"jti": ""},
])
def test_rejects_invalid_identity_claims(harness: Harness, changes: JsonObject) -> None:
    with pytest.raises(GatewayError) as error:
        harness.verifier.verify(harness.token(changes))
    assert error.value.status == 401


@pytest.mark.parametrize("header", [{"alg": "none"}, {"alg": "HS256"}, {"kid": "unknown"}, {"crit": ["unknown"]}])
def test_rejects_untrusted_headers(harness: Harness, header: JsonObject) -> None:
    with pytest.raises(GatewayError, match="OIDC"):
        harness.verifier.verify(harness.token(header_changes=header))


def test_rejects_forged_signature_and_malformed_tokens(harness: Harness) -> None:
    valid = harness.token()
    header, payload, _ = valid.split(".")
    forged = f"{header}.{payload}.{base64url(bytes(256))}"
    for token in [forged, "", "x.y.z", "x" * 17000]:
        with pytest.raises(GatewayError):
            harness.verifier.verify(token)


def test_optional_repository_allowlist(harness: Harness) -> None:
    verifier = Verifier(replace(harness.config, allowed_repository_ids=frozenset({"999"})), harness.transport, harness.clock)
    with pytest.raises(GatewayError):
        verifier.verify(harness.token())


@pytest.mark.parametrize("changes", [
    {"repo_url": "https://github.com/Other/Plugin"}, {"title": "arbitrary"},
    {"kind": "unknown"}, {"release_tag": "main"}, {"release_tag": "v01.0.0"},
    {"asset_name": "../Plugin.dll"}, {"asset_name": "a\\Plugin.dll"},
    {"asset_name": "file.pak"}, {"asset_name": "Plugin.dll\n"},
])
def test_rejects_arbitrary_payload_and_invalid_fields(harness: Harness, changes: JsonObject) -> None:
    with pytest.raises(GatewayError) as error:
        harness.service.register(harness.token(), BODY | changes)
    assert error.value.status == 400
    assert not harness.transport.issues


def test_tag_must_match_token(harness: Harness) -> None:
    with pytest.raises(GatewayError) as error:
        harness.service.register(harness.token(), BODY | {"release_tag": "v2.0.0"})
    assert error.value.status == 403


def test_registration_creates_exact_issue_with_limited_app_token(harness: Harness) -> None:
    issue = harness.service.register(harness.token(), BODY)
    assert issue.url == "https://github.com/RegistryOrg/Registry/issues/1"
    creates = [(url, token, body) for method, url, token, body in harness.transport.calls if method == "POST"]
    assert creates[0][2] == {"repositories": ["Registry"], "permissions": {"issues": "write"}}
    jwt = creates[0][1]
    header, payload, signature = jwt.split(".")
    harness.key.public_key().verify(unbase64(signature), f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    claims = json_object(decode_json(unbase64(payload).decode()))
    assert claims == {"iat": NOW - 60, "exp": NOW + 540, "iss": "456"}
    body = creates[1][2]
    assert body is not None
    assert body["title"] == "[DLL RELEASE] Plugin Version v1.0.0"
    assert body["body"] == '<!-- c2modregistry:Publisher/Plugin:v1.0.0:plugin -->\n\n```json\n{\n  "action": "add-dll-release",\n  "repo_url": "https://github.com/Publisher/Plugin",\n  "release_tag": "v1.0.0",\n  "dll_file": "Plugin.dll"\n}\n```\n'


@pytest.mark.parametrize("field", ["id", "owner", "private", "sha", "draft", "tag_name", "assets"])
def test_rechecks_public_identity_commit_and_release(harness: Harness, field: str) -> None:
    if field == "id":
        harness.transport.repo["id"] = 999
    elif field == "owner":
        harness.transport.repo["owner"] = {"id": 999}
    elif field == "private":
        harness.transport.repo["private"] = True
    elif field == "sha":
        harness.transport.commit["sha"] = "c" * 40
    elif field == "draft":
        harness.transport.release["draft"] = True
    elif field == "tag_name":
        harness.transport.release["tag_name"] = "v2.0.0"
    else:
        harness.transport.release["assets"] = []
    with pytest.raises(GatewayError):
        harness.service.register(harness.token(), BODY)
    assert not harness.transport.issues


@pytest.mark.parametrize("asset", [
    {"name": "Plugin.dll", "state": "new", "size": 1},
    {"name": "Plugin.dll", "state": "uploaded", "size": 0},
    {"name": "plugin.dll", "state": "uploaded", "size": 1},
])
def test_rejects_incomplete_empty_or_mismatched_assets(harness: Harness, asset: JsonObject) -> None:
    harness.transport.release["assets"] = [asset]
    with pytest.raises(GatewayError):
        harness.service.register(harness.token(), BODY)


@pytest.mark.parametrize("state,size", [("starter", 0), ("uploaded", 0), ("starter", 1), ("uploaded", 1)])
def test_dll_cardinality_precedes_upload_filtering(harness: Harness, state: str, size: int) -> None:
    harness.transport.release["assets"] = [
        {"name": "Plugin.dll", "state": "uploaded", "size": 123},
        {"name": "Other.DLL", "state": state, "size": size},
    ]
    with pytest.raises(GatewayError, match="exactly one DLL"):
        harness.service.register(harness.token(), {"kind": "plugin", "release_tag": TAG})
    assert not harness.transport.issues
    # Preflight failure consumes the token, but not issue deduplication.
    with pytest.raises(GatewayError, match="OIDC token already used"):
        harness.service.register(harness.token(), BODY)
    issue = harness.service.register(harness.token({"jti": "explicit-selection"}), BODY)
    assert issue.url
    assert '"dll_file": "Plugin.dll"' in str(harness.transport.issues[0]["body"])


def test_ambiguous_dll_selection_and_pak_request(harness: Harness) -> None:
    harness.transport.release["assets"] = [
        {"name": "Plugin.dll", "state": "uploaded", "size": 1},
        {"name": "Other.dll", "state": "uploaded", "size": 1},
    ]
    identity = harness.verifier.verify(harness.token())
    with pytest.raises(GatewayError):
        harness.app.verify_release(identity, Registration("plugin", TAG, ""))
    harness.app.verify_release(identity, Registration("plugin", TAG, "Other.dll"))
    harness.transport.release["assets"] = [{"name": "Mod.pak", "state": "uploaded", "size": 1}]
    issue = harness.service.register(harness.token(), {"kind": "mod", "release_tag": TAG})
    assert issue.url
    assert '"action": "add-package-release"' in str(harness.transport.issues[0]["body"])


def test_persistent_deduplication_and_conflicting_requests(harness: Harness) -> None:
    first = harness.service.register(harness.token(), BODY)
    service = Service(harness.config, harness.verifier, harness.app, harness.clock)
    assert service.register(harness.token({"jti": "token-2"}), BODY) == first
    assert len(harness.transport.issues) == 1
    with pytest.raises(GatewayError) as error:
        service.register(harness.token({"jti": "token-3"}), BODY | {"asset_name": "Other.dll"})
    assert error.value.status == 409


def test_parallel_requests_create_one_issue(harness: Harness) -> None:
    token = harness.token()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: harness.service.register(token, BODY), range(4)))
    assert len({issue.url for issue in results}) == 1
    assert len(harness.transport.issues) == 1


def test_reuses_existing_closed_issue_after_lost_local_state(harness: Harness) -> None:
    first = harness.service.register(harness.token(), BODY)
    harness.transport.issues[0]["state"] = "closed"
    next(harness.config.state_directory.joinpath("requests").glob("*.json")).unlink()
    assert harness.service.register(harness.token({"jti": "token-2"}), BODY) == first
    assert len(harness.transport.issues) == 1


@pytest.mark.parametrize("state", ["open", "closed"])
@pytest.mark.parametrize("asset", ["", "Plugin.dll"])
def test_recovers_compatible_manual_or_direct_payload(harness: Harness, state: str, asset: str) -> None:
    payload: JsonObject = {"action": "add-dll-release", "repo_url": f"https://github.com/{REPO}", "release_tag": TAG, "description": "manual notes"}
    if asset:
        payload["dll_file"] = asset
    harness.transport.issues = [{"html_url": "https://github.com/RegistryOrg/Registry/issues/99", "state": state,
        "body": f"<!-- c2modregistry:{REPO}:{TAG} -->\nManual request\n```\n{json.dumps(payload)}\n```\n"}]
    result = harness.service.register(harness.token(), {"kind": "plugin", "release_tag": TAG, "asset_name": asset})
    assert result.url.endswith("/99")
    assert len(harness.transport.issues) == 1
    assert len(list((harness.config.state_directory / "requests").glob("*.json"))) == 1


def test_creation_failure_is_retryable_with_fresh_token(harness: Harness) -> None:
    harness.transport.fail_creation = True
    with pytest.raises(GatewayError):
        harness.service.register(harness.token(), BODY)
    assert not list(harness.config.state_directory.joinpath("requests").glob("*.json"))
    harness.transport.fail_creation = False
    with pytest.raises(GatewayError) as replay:
        harness.service.register(harness.token(), BODY)
    assert replay.value.status == 409
    assert harness.service.register(harness.token({"jti": "fresh-token"}), BODY).url


def test_conflicting_recovery_does_not_poison_request_ledger(harness: Harness) -> None:
    first = harness.service.register(harness.token(), BODY)
    next((harness.config.state_directory / "requests").glob("*.json")).unlink()
    harness.transport.release["assets"] = [
        {"name": name, "state": "uploaded", "size": 123} for name in ("Plugin.dll", "Other.dll")
    ]
    restarted = Service(harness.config, harness.verifier, harness.app, harness.clock)
    with pytest.raises(GatewayError) as error:
        restarted.register(harness.token({"jti": "different-selection"}), BODY | {"asset_name": "Other.dll"})
    assert error.value.status == 409
    assert not list((harness.config.state_directory / "requests").glob("*.json"))
    assert restarted.register(harness.token({"jti": "original-selection"}), BODY) == first
    record = json_object(decode_json(next((harness.config.state_directory / "requests").glob("*.json")).read_text()))
    assert record["asset"] == "Plugin.dll"
    assert len(harness.transport.issues) == 1


@pytest.mark.parametrize("changes", [
    {"action": "add-package-release"}, {"repo_url": "https://github.com/Other/Plugin"},
    {"release_tag": "v2.0.0"}, {"dll_file": "Other.dll"}, {"dll_file": None},
])
def test_recovered_manual_payload_must_match_before_persistence(harness: Harness, changes: JsonObject) -> None:
    payload: JsonObject = {"action": "add-dll-release", "repo_url": f"https://github.com/{REPO}", "release_tag": TAG, "dll_file": "Plugin.dll"}
    payload.update(changes)
    harness.transport.issues = [{"html_url": "existing", "body": f"<!-- c2modregistry:{REPO}:{TAG} -->\n\n```json\n{json.dumps(payload)}\n```\n"}]
    with pytest.raises(GatewayError) as error:
        harness.service.register(harness.token(), BODY)
    assert error.value.status == 409
    assert not list((harness.config.state_directory / "requests").glob("*.json"))


@pytest.mark.parametrize("body", ["marker only", "```json\n{bad}\n```", "```\nnull\n```", "```\n[]\n```"])
def test_recovered_malformed_payload_fails_closed(harness: Harness, body: str) -> None:
    harness.transport.issues = [{"html_url": "existing", "body": f"<!-- c2modregistry:{REPO}:{TAG} -->\n{body}"}]
    with pytest.raises(GatewayError) as error:
        harness.service.register(harness.token(), BODY)
    assert error.value.status == 409
    assert not list((harness.config.state_directory / "requests").glob("*.json"))


@pytest.mark.parametrize("asset", ["", "Client.pak"])
@pytest.mark.parametrize("second_state,second_size", [("uploaded", 123), ("new", 0)])
def test_gateway_rejects_ambiguous_paks_before_issue_creation(harness: Harness, asset: str, second_state: str, second_size: int) -> None:
    harness.transport.release["assets"] = [
        {"name": "Client.pak", "state": "uploaded", "size": 123},
        {"name": "Server.pak", "state": second_state, "size": second_size},
    ]
    with pytest.raises(GatewayError, match="Multiple pak files") as error:
        harness.service.register(harness.token(), {"kind": "mod", "release_tag": TAG, "asset_name": asset})
    assert error.value.status == 422
    assert not harness.transport.issues
    assert not list((harness.config.state_directory / "requests").glob("*.json"))


@pytest.mark.parametrize("asset", ["", "Client.pak"])
def test_gateway_preserves_single_pak_wire_contract(harness: Harness, asset: str) -> None:
    harness.transport.release["assets"] = [{"name": "Client.pak", "state": "uploaded", "size": 123}]
    harness.service.register(harness.token(), {"kind": "mod", "release_tag": TAG, "asset_name": asset})
    from mod_registry_core.registration import parse_registration_payload
    assert parse_registration_payload(str(harness.transport.issues[0]["body"])) == {
        "action": "add-package-release", "repo_url": f"https://github.com/{REPO}", "release_tag": TAG,
    }


@pytest.mark.parametrize("asset", ["", "Client.PAK"])
def test_gateway_preserves_registry_case_sensitive_pak_rule(harness: Harness, asset: str) -> None:
    harness.transport.release["assets"] = [{"name": "Client.PAK", "state": "uploaded", "size": 123}]
    with pytest.raises(GatewayError, match="No pak file") as error:
        harness.service.register(harness.token(), {"kind": "mod", "release_tag": TAG, "asset_name": asset})
    assert error.value.status == 422
    assert not harness.transport.issues


def test_rate_limit_persists_and_expires(harness: Harness) -> None:
    config = replace(harness.config, requests_per_hour=1)
    service = Service(config, harness.verifier, harness.app, harness.clock)
    harness.transport.fail_creation = True
    with pytest.raises(GatewayError):
        service.register(harness.token(), BODY)
    restarted = Service(config, harness.verifier, harness.app, harness.clock)
    with pytest.raises(GatewayError) as error:
        restarted.register(harness.token({"jti": "token-2"}), BODY)
    assert error.value.status == 429
    harness.clock.now += 3601
    harness.transport.fail_creation = False
    assert restarted.register(harness.token({"jti": "token-3"}), BODY).url


def test_wrong_installation_owner_fails_without_creating_issue(harness: Harness) -> None:
    harness.transport.account = "OtherOwner"
    with pytest.raises(GatewayError) as error:
        harness.service.register(harness.token(), BODY)
    assert error.value.status == 503
    assert not harness.transport.issues


@pytest.mark.parametrize("fields", [
    {"audience": "http://example.com/registrations"}, {"audience": "https://user:secret@example.com"},
    {"registry": "../Registry"}, {"app_id": "bad"}, {"requests_per_hour": 0},
])
def test_configuration_rejects_invalid_values(harness: Harness, fields: dict[str, str | int]) -> None:
    # Explicitly reconstruct typed fields without dynamic dataclass kwargs.
    audience = fields.get("audience", harness.config.audience)
    registry = fields.get("registry", harness.config.registry)
    app_id = fields.get("app_id", harness.config.app_id)
    limit = fields.get("requests_per_hour", 20)
    assert isinstance(audience, str) and isinstance(registry, str) and isinstance(app_id, str) and isinstance(limit, int)
    with pytest.raises(ValueError):
        Config(audience, registry, app_id, "123", harness.config.private_key_file, harness.config.state_directory, requests_per_hour=limit)


def test_http_registration_and_health(harness: Harness) -> None:
    with GatewayServer(("127.0.0.1", 0), harness.service) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        try:
            assert requests.get(f"{endpoint}/healthz", timeout=5).status_code == 200
            response = requests.post(f"{endpoint}/registrations", headers={"Authorization": f"Bearer {harness.token()}"}, json=BODY, timeout=5)
            assert response.status_code == 200
            assert json_object(decode_json(response.text))["issue_url"] == "https://github.com/RegistryOrg/Registry/issues/1"
            harness.transport.release["assets"] = [
                {"name": name, "state": "uploaded", "size": 123} for name in ("Plugin.dll", "Mod.pak")
            ]
            mod: JsonObject = {"kind": "mod", "release_tag": TAG, "asset_name": "Mod.pak"}
            assert requests.post(f"{endpoint}/registrations", headers={"Authorization": f"Bearer {harness.token()}"}, json=mod, timeout=5).status_code == 409
            response = requests.post(f"{endpoint}/registrations", headers={"Authorization": f"Bearer {harness.token({'jti': 'mod-token'})}"}, json=mod, timeout=5)
            assert response.status_code == 200
            assert json_object(decode_json(response.text))["issue_url"] == "https://github.com/RegistryOrg/Registry/issues/2"
            assert requests.post(f"{endpoint}/registrations", json=BODY, timeout=5).status_code == 401
            assert requests.post(f"{endpoint}/other", json=BODY, timeout=5).status_code == 404
            assert requests.post(f"{endpoint}/registrations", data="{}", timeout=5).status_code == 415
            assert requests.post(f"{endpoint}/registrations", headers={"Content-Type": "application/json"}, data="x" * 17000, timeout=5).status_code == 413
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("first_kind", ["plugin", "mod"])
@pytest.mark.parametrize("legacy", [False, True])
def test_mixed_release_dual_registration_restart_and_recovery(harness: Harness, first_kind: str, legacy: bool) -> None:
    from mod_registry_core.registration import parse_registration_payload
    harness.transport.release["assets"] = [
        {"name": name, "state": "uploaded", "size": 123} for name in ("Plugin.dll", "Other.dll", "Mod.pak")
    ]
    requests_by_kind: dict[str, JsonObject] = {
        "plugin": BODY, "mod": {"kind": "mod", "release_tag": TAG, "asset_name": "Mod.pak"},
    }
    second_kind = "mod" if first_kind == "plugin" else "plugin"
    first = harness.service.register(harness.token(), requests_by_kind[first_kind])
    if legacy:
        path = next((harness.config.state_directory / "requests").glob("*.json"))
        legacy_key = hashlib.sha256(f"321:{TAG}".encode()).hexdigest()
        path.rename(path.with_name(f"{legacy_key}.json"))
        harness.transport.issues[0]["body"] = str(harness.transport.issues[0]["body"]).replace(f":{first_kind} -->", " -->")
    restarted = Service(harness.config, harness.verifier, harness.app, harness.clock)
    assert restarted.register(harness.token(), requests_by_kind[first_kind]) == first
    # Token-wide replay protection also applies across kinds.
    with pytest.raises(GatewayError, match="OIDC token already used"):
        restarted.register(harness.token(), requests_by_kind[second_kind])
    second = restarted.register(harness.token({"jti": "second-kind"}), requests_by_kind[second_kind])
    assert first != second
    assert len(harness.transport.issues) == 2
    payloads = [parse_registration_payload(str(issue["body"])) for issue in harness.transport.issues]
    assert {str(payload["action"]) for payload in payloads} == {"add-dll-release", "add-package-release"}
    assert next(payload for payload in payloads if payload["action"] == "add-dll-release")["dll_file"] == "Plugin.dll"
    assert "dll_file" not in next(payload for payload in payloads if payload["action"] == "add-package-release")
    for path in (harness.config.state_directory / "requests").glob("*.json"):
        path.unlink()
    if legacy:
        for issue in harness.transport.issues:
            issue["body"] = str(issue["body"]).replace(":plugin -->", " -->").replace(":mod -->", " -->")
    harness.transport.issues.reverse()  # Recovery must not depend on issue order.
    for kind, expected in [(first_kind, first), (second_kind, second)]:
        assert restarted.register(harness.token({"jti": f"recover-{kind}"}), requests_by_kind[kind]) == expected
    assert len(harness.transport.issues) == 2


def test_legacy_ledger_conflicting_asset_remains_rejected(harness: Harness) -> None:
    harness.service.register(harness.token(), BODY)
    path = next((harness.config.state_directory / "requests").glob("*.json"))
    legacy_key = hashlib.sha256(f"321:{TAG}".encode()).hexdigest()
    path.rename(path.with_name(f"{legacy_key}.json"))
    with pytest.raises(GatewayError, match="different request"):
        harness.service.register(harness.token({"jti": "other"}), BODY | {"asset_name": "Other.dll"})


def test_parallel_mixed_requests_create_one_issue_per_kind(harness: Harness) -> None:
    harness.transport.release["assets"] = [
        {"name": name, "state": "uploaded", "size": 123} for name in ("Plugin.dll", "Mod.pak")
    ]
    mod: JsonObject = {"kind": "mod", "release_tag": TAG, "asset_name": "Mod.pak"}
    requests_by_kind = [(harness.token(), BODY), (harness.token({"jti": "parallel-mod"}), mod)] * 3
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda item: harness.service.register(*item), requests_by_kind))
    assert len({issue.url for issue in results}) == 2
    assert len(harness.transport.issues) == 2
    assert len(list((harness.config.state_directory / "requests").glob("*.json"))) == 2
