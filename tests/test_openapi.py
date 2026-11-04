"""Validate the GitHub route contract and its unchanged real-registry payloads."""
from pathlib import Path
import socket
import tarfile

from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
import pytest

from generated_models.json_types import JsonObject, decode_json, json_object
from generated_models.schema_documents import read_document
from tests.test_registry_reference import ARCHIVE, COMMIT


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "openapi.yaml"


def at(document: JsonObject, *keys: str) -> JsonObject:
    for key in keys:
        document = json_object(document[key])
    return document


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(connection: socket.socket, address: str | tuple[str, int] | tuple[str, int, int, int]) -> None:
        raise AssertionError("OpenAPI references must resolve without the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def test_openapi_validates_offline() -> None:
    validate(read_document(SPEC), base_uri=SPEC.as_uri())


@pytest.mark.parametrize("method", ["get", "head"])
def test_release_operations_use_publisher_repository(method: str) -> None:
    spec = read_document(SPEC)
    route = "/{owner}/{repository}/releases/download/{tag}/{asset}"
    servers = at(spec, "paths", route, method)["servers"]
    assert isinstance(servers, list) and len(servers) == 1
    url = str(json_object(servers[0])["url"]) + route.format(
        owner="OtherPublisher", repository="SomeMod", tag="v1.2.3", asset="SomeMod.pak",
    )
    assert url == "https://github.com/OtherPublisher/SomeMod/releases/download/v1.2.3/SomeMod.pak"


@pytest.mark.parametrize("database,index,count", [
    ("package_db", "mod_list_index.txt", 19),
    ("dll_db", "plugin_list_index.txt", 1),
])
def test_openapi_routes_match_pinned_registry(database: str, index: str, count: int) -> None:
    spec = read_document(SPEC)
    documents: JsonObject = {}
    for path in (ROOT / "schemas").glob("*.schema.yaml"):
        schema = read_document(path)
        documents[path.name] = schema
        # Also index the full document by file URI so fragment pointers resolve.
        documents[path.name + "-local"] = {**schema, "$id": path.as_uri()}
    route = f"/{database}/packages/{{owner}}/{{repository}}.json"
    response_schema = at(spec, "paths", route, "get", "responses", "200", "content", "text/plain", "schema")
    # Keep components at the document root so local JSON pointers retain their
    # OpenAPI scope. Embedded schema resources make resolution offline.
    validation_schema: JsonObject = {
        "$id": SPEC.as_uri(), "components": spec["components"], "$defs": documents, **response_schema,
    }
    validator = Draft202012Validator(validation_schema)
    prefix = f"C2ModRegistry-{COMMIT}"
    assert at(spec, "paths", f"/{database}/{index}", "get", "responses", "200") == {
        "$ref": "#/components/responses/PackageList"
    }
    with tarfile.open(ARCHIVE) as archive:
        stream = archive.extractfile(f"{prefix}/{database}/{index}")
        assert stream is not None
        body = stream.read().decode()
        Draft202012Validator(at(spec, "components", "responses", "PackageList", "content", "text/plain", "schema")).validate(body)
        packages = body.splitlines()
        assert len(packages) == count
        for package in packages:
            owner, repository = package.split("/")
            package_path = route.format(owner=owner, repository=repository)
            stream = archive.extractfile(f"{prefix}{package_path}")
            assert stream is not None, package_path
            validator.validate(decode_json(stream.read().decode()))
