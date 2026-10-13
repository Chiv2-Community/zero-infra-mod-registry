"""Persistent request deduplication and rate limiting."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from automated_registry_gateway.github import GithubApp
from automated_registry_gateway.models import Config, GatewayError, Identity, Issue, Registration
from automated_registry_gateway.oidc import Verifier
from mod_registry_core.json_types import JsonObject, decode_json, json_array, json_int, json_object, json_string


def atomic_write(path: Path, data: JsonObject) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Service:
    def __init__(self, config: Config, verifier: Verifier, github: GithubApp, clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.verifier = verifier
        self.github = github
        self.clock = clock
        self.lock = threading.Lock()
        config.state_directory.mkdir(parents=True, exist_ok=True)
        (config.state_directory / "requests").mkdir(exist_ok=True)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        # One persistent store per registry. Serialize writes across threads and
        # processes; never hold an in-memory-only deduplication decision.
        with self.lock, (self.config.state_directory / "lock").open("a") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _rate_limit(self, identity: Identity) -> None:
        path = self.config.state_directory / "rate-limits.json"
        data = json_object(decode_json(path.read_text())) if path.exists() else {"events": []}
        cutoff = int(self.clock()) - 3600
        events = [json_object(value) for value in json_array(data.get("events"))]
        events = [event for event in events if json_int(event.get("time")) > cutoff]
        if any(event.get("token_id") == identity.token_id for event in events):
            raise GatewayError(409, "OIDC token already used; obtain a new token to retry")
        if len(events) >= self.config.global_requests_per_hour or sum(event.get("repository_id") == identity.repository_id for event in events) >= self.config.requests_per_hour:
            raise GatewayError(429, "Registration request rate limit exceeded")
        events.append({"time": int(self.clock()), "repository_id": identity.repository_id, "token_id": identity.token_id})
        document: JsonObject = {"events": list(events)}
        atomic_write(path, document)

    def register(self, token: str, data: JsonObject) -> Issue:
        identity = self.verifier.verify(token)
        try:
            request = Registration.from_json(data)
        except ValueError as error:
            raise GatewayError(400, str(error)) from error
        if request.tag != identity.tag:
            raise GatewayError(403, "Requested release must match the authenticated workflow tag")
        key = hashlib.sha256(f"{identity.repository_id}:{request.tag}:{request.kind}".encode()).hexdigest()
        path = self.config.state_directory / "requests" / f"{key}.json"
        with self._exclusive():
            legacy_key = hashlib.sha256(f"{identity.repository_id}:{request.tag}".encode()).hexdigest()
            legacy_path = path.with_name(f"{legacy_key}.json")
            record = json_object(decode_json(path.read_text())) if path.exists() else None
            if record is None and legacy_path.exists():
                legacy = json_object(decode_json(legacy_path.read_text()))
                if legacy.get("kind") not in {"plugin", "mod"}:
                    raise GatewayError(409, "Invalid legacy request state; repair the registry ledger")
                if legacy.get("kind") == request.kind:
                    record = legacy
            if record is not None:
                # Do not silently change selected assets on an already-created request.
                if record.get("kind") != request.kind or record.get("asset") != request.asset:
                    raise GatewayError(409, "This tag already has a different request; edit its registry issue")
                if not path.exists():
                    atomic_write(path, record)
                return Issue(json_string(record.get("issue_url")))
            self._rate_limit(identity)
            self.github.verify_release(identity, request)
            issue = self.github.create_issue(identity, request)
            atomic_write(path, {"kind": request.kind, "asset": request.asset, "issue_url": issue.url})
            return issue
