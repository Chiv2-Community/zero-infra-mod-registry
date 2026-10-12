import json

import pytest
import requests

from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.utils.json_types import JsonObject
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, response_fixture


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
def test_uploaded_metadata_takes_precedence(filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded_url = f"https://example.com/releases/{filename}"
    release = FakeRelease(assets=[FakeAsset(name=filename, browser_download_url=uploaded_url)])
    metadata: JsonObject = {"name": "Updated", "description": "Patched description", "authors": ["Author"],
                            "mod_dependencies": [{"repo_url": "https://github.com/Test/Pak", "version": "^2.0.0"}]}
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert timeout == 60 and url == uploaded_url
        return response_fixture(json.dumps(metadata).encode(), url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    assert retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename) == metadata
    assert calls == [uploaded_url]


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
def test_metadata_asset_names_are_exact(filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(tag_name="v1.0.0-RC2", assets=[FakeAsset(name=filename.upper()), FakeAsset(name=f"nested/{filename}")])
    expected = f"https://raw.githubusercontent.com/Test/Plugin/v1.0.0-RC2/{filename}"

    def get(url: str, *, timeout: int) -> requests.Response:
        assert url == expected and timeout == 60
        return response_fixture(b"{}", url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    assert retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename) == {}


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
@pytest.mark.parametrize("status,body", [(404, b"missing"), (500, b"error"), (200, b"invalid JSON"), (200, b"[]")])
def test_invalid_uploaded_metadata_never_falls_back(filename: str, status: int, body: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded_url = f"https://example.com/{filename}"
    release = FakeRelease(assets=[FakeAsset(name=filename, browser_download_url=uploaded_url)])
    calls: list[str] = []

    def get(url: str, *, timeout: int) -> requests.Response:
        calls.append(url)
        assert url == uploaded_url
        return response_fixture(body, url, status=status)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    with pytest.raises((ValueError, requests.HTTPError)):
        retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename)
    assert calls == [uploaded_url]


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
def test_duplicate_metadata_assets_fail_before_download(filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(assets=[FakeAsset(name=filename), FakeAsset(name=filename)])

    def get(url: str, *, timeout: int) -> requests.Response:
        raise AssertionError("Ambiguous metadata must not be downloaded")

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    with pytest.raises(ValueError, match="multiple"):
        retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename)


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
@pytest.mark.parametrize("url", ["http://example.com/file.json", "https://user:password@example.com/file.json"])
def test_unsafe_metadata_sources_are_rejected(filename: str, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(assets=[FakeAsset(name=filename, browser_download_url=url)])

    def get(url: str, *, timeout: int) -> requests.Response:
        raise AssertionError("Unsafe metadata source must not be downloaded")

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    with pytest.raises(ValueError, match="HTTPS"):
        retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename)


@pytest.mark.parametrize("filename", ["mod.json", "plugin.json"])
@pytest.mark.parametrize("url", ["http://example.com/file.json", "https://user:password@example.com/file.json"])
def test_unsafe_metadata_redirects_are_rejected(filename: str, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    release = FakeRelease(assets=[FakeAsset(name=filename, browser_download_url=f"https://example.com/{filename}")])

    def get(source_url: str, *, timeout: int) -> requests.Response:
        return response_fixture(b"{}", url)

    monkeypatch.setattr(requests, "get", get)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    with pytest.raises(ValueError, match="redirect"):
        retriever._fetch_release_json(Repo("Test", "Plugin"), release.as_release(), filename)
