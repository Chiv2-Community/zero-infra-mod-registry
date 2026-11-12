import json
from pathlib import Path
import subprocess

import pytest
import requests
from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from generated_models.metadata import Mod
from zero_infra_mod_registry.models.loading import load, serialize
from generated_models.json_types import JsonObject
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, response_fixture


@pytest.mark.parametrize("uploaded", [False, True])
@pytest.mark.parametrize("tag", ["v1.0.0", "1.0.0", "v1.0.0-rc.1", "v1.0.0+build.42", "v1.0.0-rc.1+build.42"])
@pytest.mark.parametrize("version_prefix", [None, ""])
def test_process_release_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploaded: bool, tag: str, version_prefix: str | None) -> None:
    repo = Repo("Test", "Plugin")
    release = FakeRelease(tag_name=tag, assets=[FakeAsset(name="test.pak")])
    version = None if version_prefix is None else version_prefix + tag.removeprefix("v")
    metadata_url = "https://example.com/mod.json" if uploaded else f"https://raw.githubusercontent.com/Test/Plugin/{tag}/mod.json"
    if uploaded:
        release.assets.append(FakeAsset(name="mod.json", browser_download_url=metadata_url))
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())
    calls: list[str] = []
    metadata: JsonObject = {"name": "Test Mod", "description": "Description", "authors": ["Author"], "dependencies": []}
    if version is not None:
        metadata["version"] = version

    def get(url: str, *, stream: bool = False, timeout: int = 60) -> requests.Response:
        calls.append(url)
        if not stream:
            assert url == metadata_url and timeout == 60
        return response_fixture(b"pak content" if stream else json.dumps(metadata).encode(), url)

    def scan(args: list[str], *, check: bool, capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        assert check and capture_output and text
        output = Path(args[args.index("--out") + 1])
        assert (output / "test.pak").read_bytes() == b"pak content"
        scanner: JsonObject = {"paks": [{"pak_name": "test.pak", "pak_path": "test.pak", "pak_hash": "abc123hash",
                                       "inventory": {"markers": [], "blueprints": [], "maps": [], "replacements": [], "arbitrary": []}}]}
        (output / "manifest.json").write_text(json.dumps(scanner))
        return subprocess.CompletedProcess(args, 0, "", "")

    scanner = tmp_path / "scanner"
    scanner.touch()
    monkeypatch.setenv("UNCHAINED_SCANNER_PATH", str(scanner))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(subprocess, "run", scan)
    result = retriever.process_release(repo, release.as_release())
    assert result.tag == tag and result.hash == "abc123hash"
    assert result.info.name == "Test Mod" and result.info.repo_url == repo.github_url()
    expected_version = version if version is not None else tag.removeprefix("v")
    assert result.info.version == expected_version
    package = Mod(result.info, [result])
    wire = serialize(package)
    assert wire["latest_release_info"] == serialize(result.info)
    assert serialize(result.info)["version"] == expected_version
    assert load(wire, Mod) == package
    assert result.release_notes_markdown == "Release notes"
    assert len(calls) == 2
    assert calls[0] == metadata_url


def test_process_release_no_mod_json(monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease()
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())

    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(b"not found", url, status=404)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(Exception, match="mod.json does not exist"):
        retriever.process_release(Repo("Test", "Plugin"), release.as_release())


@pytest.mark.parametrize("names,message", [
    (["Client.pak", "Server.pak"], "Multiple pak files"),
    (["Client.PAK"], "No pak file"),
])
def test_process_release_preserves_pak_cardinality_and_case_boundary(monkeypatch: pytest.MonkeyPatch, names: list[str], message: str) -> None:
    release = FakeRelease(assets=[FakeAsset(name=name) for name in names])
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())
    metadata: JsonObject = {"name": "Test Mod", "description": "Description", "authors": ["Author"], "dependencies": []}

    def get(url: str, *, timeout: int) -> requests.Response:
        return response_fixture(json.dumps(metadata).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(Exception, match=message):
        retriever.process_release(Repo("Test", "Plugin"), release.as_release())
