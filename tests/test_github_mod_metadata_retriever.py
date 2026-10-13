from datetime import datetime

import pytest
from github.GitRelease import GitRelease
from zero_infra_mod_registry.models import Dependency, Mod, Release, Repo
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from tests.fakes import FakeAsset, FakeGithub, FakeRelease, mod_fixture


@pytest.fixture()
def retriever() -> GithubModMetadataRetriever:
    return GithubModMetadataRetriever(FakeGithub([]).as_github())


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0.0", "1.2.3-beta.1"])
def test_validate_version_tag_name(retriever: GithubModMetadataRetriever, tag: str) -> None:
    assert retriever.validate_version_tag_name(tag) is None


@pytest.mark.parametrize("tag", ["version1", "v"])
def test_invalid_version_tag_name(retriever: GithubModMetadataRetriever, tag: str) -> None:
    error = retriever.validate_version_tag_name(tag)
    assert error is not None and tag.lstrip("v") in error


@pytest.mark.parametrize("version", ["1.0.0", "v1.0.0", "^1.0.0", ">=1.0.0,<2.0.0"])
def test_validate_dependency_versions(retriever: GithubModMetadataRetriever, version: str) -> None:
    assert retriever.validate_dependency_versions([Dependency("https://github.com/Test/Plugin", version)]) == []


@pytest.mark.parametrize("version", ["invalid", "v"])
def test_invalid_dependency_versions(retriever: GithubModMetadataRetriever, version: str) -> None:
    errors = retriever.validate_dependency_versions([Dependency("https://github.com/Test/Plugin", version)])
    assert len(errors) == 1 and "does not conform to the semver spec" in errors[0]


def test_find_pak_file(retriever: GithubModMetadataRetriever) -> None:
    pak = FakeAsset(name="mod.pak")
    release = FakeRelease(assets=[pak, FakeAsset(name="readme.md")])
    assert retriever.find_pak_file(release.as_release()) is pak.as_asset()
    release.assets = []
    error = retriever.find_pak_file(release.as_release())
    assert isinstance(error, str) and "No pak file found" in error
    release.assets = [pak, FakeAsset(name="other.pak")]
    error = retriever.find_pak_file(release.as_release())
    assert isinstance(error, str) and "Multiple pak files found" in error


def test_draft_pak_release_is_rejected_before_downloading(retriever: GithubModMetadataRetriever) -> None:
    with pytest.raises(ValueError, match="Draft pak releases"):
        retriever.process_release(Repo("Test", "Plugin"), FakeRelease(draft=True).as_release())


def test_first_registration_fetches_only_requested_release(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeGithub([FakeRelease(tag_name="v1.0.0"), FakeRelease(tag_name="v1.1.0")])
    retriever = GithubModMetadataRetriever(client.as_github())
    calls: list[str] = []

    def process(repo: Repo, release: GitRelease) -> Release:
        assert repo == Repo("Test", "Plugin")
        calls.append(release.tag_name)
        date = datetime(2023, 1 if release.tag_name == "v1.0.0" else 2, 1)
        return mod_fixture(tag=release.tag_name, date=date).releases[0]

    monkeypatch.setattr(retriever, "process_release", process)
    release = retriever.fetch_release_metadata(Repo("Test", "Plugin"), "v1.0.0")
    assert release is not None and release.tag == "v1.0.0"
    assert calls == ["v1.0.0"]
    assert client.repository.tag_calls == ["v1.0.0"]
    assert client.repo_calls == ["Test/Plugin"]


def test_update_mod_with_release(retriever: GithubModMetadataRetriever) -> None:
    first = mod_fixture(date=datetime(2023, 1, 1))
    second = mod_fixture(tag="v1.1.0", date=datetime(2023, 2, 1))
    third = mod_fixture(tag="v1.2.0", date=datetime(2023, 3, 1))
    updated = retriever.update_mod_with_release(Mod(second.latest_release_info, first.releases + second.releases), third.releases[0])
    assert [release.tag for release in updated.releases] == ["v1.2.0", "v1.1.0", "v1.0.0"]
    assert updated.latest_release_info == third.latest_release_info


def test_fetch_release_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeGithub([FakeRelease(tag_name="v1.2.0")])
    retriever = GithubModMetadataRetriever(client.as_github())
    expected = mod_fixture(tag="v1.2.0").releases[0]

    def process(repo: Repo, release: GitRelease) -> Release:
        assert repo == Repo("Test", "Plugin") and release.tag_name == "v1.2.0"
        return expected

    monkeypatch.setattr(retriever, "process_release", process)
    assert retriever.fetch_release_metadata(Repo("Test", "Plugin"), "v1.2.0") == expected
    assert client.repo_calls == ["Test/Plugin"]
    assert client.repository.tag_calls == ["v1.2.0"]
