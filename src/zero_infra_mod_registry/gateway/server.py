"""Small HTTP server intended to run behind an HTTPS reverse proxy."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import socket
from typing import override

from zero_infra_mod_registry.gateway.github import GithubApp
from zero_infra_mod_registry.gateway.models import Config, GatewayError
from zero_infra_mod_registry.gateway.oidc import Verifier
from zero_infra_mod_registry.gateway.service import Service
from zero_infra_mod_registry.gateway.transport import GithubTransport
from zero_infra_mod_registry.utils.json_types import JsonObject, decode_json, json_object


class GatewayServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], service: Service) -> None:
        self.service = service
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    connection: socket.socket

    @override
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def _respond(self, status: int, data: JsonObject) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 429:
            self.send_header("Retry-After", "3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._respond(200, {"status": "ok"}) if self.path == "/healthz" else self._respond(404, {"error": "Not found"})

    def do_POST(self) -> None:
        try:
            if self.path != "/registrations":
                raise GatewayError(404, "Not found")
            if self.headers.get("Transfer-Encoding"):
                raise GatewayError(400, "Transfer encoding is not supported")
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise GatewayError(415, "Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 16384:
                raise GatewayError(413, "Request body must be between 1 and 16384 bytes")
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                raise GatewayError(401, "GitHub OIDC bearer token required")
            body = self.rfile.read(length)
            if len(body) != length:
                raise GatewayError(400, "Incomplete request body")
            data = json_object(decode_json(body.decode("utf-8")))
            if not isinstance(self.server, GatewayServer):
                raise RuntimeError("Invalid gateway server")
            issue = self.server.service.register(authorization.removeprefix("Bearer "), data)
            self._respond(200, issue.as_json())
        except GatewayError as error:
            self._respond(error.status, {"error": str(error)})
        except (ValueError, UnicodeError):
            self._respond(400, {"error": "Invalid JSON request"})
        except (TimeoutError, socket.timeout):
            self.close_connection = True
        except Exception:
            logging.error("Registration failed; check gateway configuration and state storage")
            self._respond(503, {"error": "Registration service unavailable"})

    @override
    def log_message(self, format: str, *args: str) -> None:
        # Never log headers, tokens or request bodies. Base HTTP errors may log
        # request text. Leave access logging to the HTTPS proxy instead.
        return


class GatewayArguments(argparse.Namespace):
    check_config: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automated-registry-gateway, the optional GitHub OIDC registration service")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and private key, then exit")
    args = GatewayArguments()
    parser.parse_args(namespace=args)
    config = Config.from_environment()
    transport = GithubTransport()
    github = GithubApp(config, transport)
    if args.check_config:
        print("Gateway configuration and private key are valid")
        return
    logging.basicConfig(level=logging.INFO)
    service = Service(config, Verifier(config, transport), github)
    with GatewayServer((config.host, config.port), service) as server:
        logging.info("automated-registry-gateway listening on port %d", config.port)
        server.serve_forever()


if __name__ == "__main__":
    main()
