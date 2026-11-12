"""Shared SemVer requirement parsing and matching."""
import re

from semver import Version


def parse_semver(value: str) -> Version:
    """Parse a complete, unprefixed semantic version."""
    version = Version.parse(value)
    if str(version) != value:
        raise ValueError(f"Invalid semantic version: {value!r}")
    return version


def parse_release_version(tag: str) -> Version:
    """Strip the release tag prefix before parsing its semantic version."""
    return parse_semver(tag.removeprefix("v"))


def validate_metadata_version(version: str | None, release_tag: str) -> None:
    """Match declared metadata versions to tags without changing stored spelling."""
    if version is None:
        return
    declared = str(parse_semver(version))
    released = str(parse_release_version(release_tag))
    if declared != released:
        raise ValueError(f"version {version!r} does not match release tag {release_tag!r}")


def parse_version_requirement(requirement: str) -> tuple[str, ...]:
    requirement = requirement.removeprefix("v")
    if requirement.startswith("^"):
        base = Version.parse(requirement[1:])
        upper = Version(base.major + 1, 0, 0) if base.major else (
            Version(0, base.minor + 1, 0) if base.minor else Version(0, 0, base.patch + 1))
        return f">={base}", f"<{upper}"
    comparisons: list[str] = []
    for part in requirement.split(","):
        match = re.fullmatch(r"(>=|<=|==|!=|>|<)?(.+)", part.strip())
        if match is None:
            raise ValueError(f"Invalid version requirement: {requirement}")
        operator = match.group(1) or "=="
        version = Version.parse(match.group(2))
        comparisons.append(f"{operator}{version}")
    return tuple(comparisons)


def dependency_matches(version: str, requirement: str) -> bool:
    candidate = Version.parse(version)
    return all(candidate.match(part) for part in parse_version_requirement(requirement))
