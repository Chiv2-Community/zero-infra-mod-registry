"""Shared SemVer requirement parsing and matching."""
import re

from semver import Version


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
