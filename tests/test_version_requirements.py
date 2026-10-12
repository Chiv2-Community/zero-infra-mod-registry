import pytest

from zero_infra_mod_registry.models import Dependency
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.utils.version_requirements import dependency_matches, parse_version_requirement
from tests.fakes import FakeGithub


@pytest.mark.parametrize("requirement,expected", [
    ("1.2.3", ("==1.2.3",)), ("v1.2.3", ("==1.2.3",)),
    (">=1.0.0, <2.0.0", (">=1.0.0", "<2.0.0")),
    ("^1.2.3", (">=1.2.3", "<2.0.0")),
    ("^0.2.3", (">=0.2.3", "<0.3.0")),
    ("^0.0.3", (">=0.0.3", "<0.0.4")),
    ("v^1.2.3", (">=1.2.3", "<2.0.0")),
    ("!=1.2.3", ("!=1.2.3",)),
])
def test_shared_requirement_parser(requirement: str, expected: tuple[str, ...]) -> None:
    assert parse_version_requirement(requirement) == expected
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    assert retriever.validate_dependency_versions([Dependency("https://github.com/Test/Pak", requirement)]) == []


@pytest.mark.parametrize("requirement", ["^1.0.0,<2.0.0", "latest", "", "1.0.0,", ">=01.0.0", "^0.0", "=1.0.0"])
def test_all_validation_paths_reject_invalid_requirements(requirement: str) -> None:
    with pytest.raises(ValueError):
        parse_version_requirement(requirement)
    with pytest.raises(ValueError):
        dependency_matches("1.0.0", requirement)
    retriever = GithubModMetadataRetriever(FakeGithub([]).as_github())
    assert len(retriever.validate_dependency_versions([Dependency("https://github.com/Test/Pak", requirement)])) == 1


@pytest.mark.parametrize("version,requirement,expected", [
    ("1.0.0", "^1.0.0", True), ("2.0.0", "^1.0.0", False),
    ("0.2.9", "^0.2.3", True), ("0.3.0", "^0.2.3", False),
    ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
    ("1.0.0-rc.1", ">=1.0.0", False), ("1.0.0-rc.2", "^1.0.0-rc.1", True),
    ("1.0.0+build", "1.0.0", True), ("1.2.3", "!=1.2.3", False),
])
def test_requirement_matching(version: str, requirement: str, expected: bool) -> None:
    assert dependency_matches(version, requirement) is expected
