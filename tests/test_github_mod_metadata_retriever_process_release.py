import json
from pathlib import Path
import subprocess

import pytest
import requests
from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.utils.json_types import JsonObject
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, response_fixture


@pytest.mark.parametrize("uploaded", [False, True])
def test_process_release_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploaded: bool) -> None:
    repo = Repo("Test", "Plugin")
    release = FakeRelease(assets=[FakeAsset(name="test.pak")])
    metadata_url = "https://example.com/mod.json" if uploaded else "https://raw.githubusercontent.com/Test/Plugin/v1.0.0/mod.json"
    if uploaded:
        release.assets.append(FakeAsset(name="mod.json", browser_download_url=metadata_url))
    retriever = GithubModMetadataRetriever(FakeGithub([release]).as_github())
    calls: list[str] = []
    metadata: JsonObject = {"name": "Test Mod", "description": "Description", "authors": ["Author"], "dependencies": []}

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
    assert result.tag == "v1.0.0" and result.hash == "abc123hash"
    assert result.info.name == "Test Mod" and result.info.repo_url == repo.github_url()
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
