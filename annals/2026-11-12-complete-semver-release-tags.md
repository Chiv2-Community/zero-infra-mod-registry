# Complete SemVer release tags before ingestion

- Date: 2026-11-12
- Status: implemented on feature branch; PR open at source response
- Scope: mod and plugin release tag and metadata version validation
- Repository: [Chiv2-Community/zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry); canonical remote `https://github.com/Chiv2-Community/zero-infra-mod-registry.git`
- Branch: `feature/mod-json-version`; recording HEAD and implementation: `5bb906b342cd4d3bf42794064877518556d5d5e3`
- Exact HEAD tag: none; nearest reachable tag: `v1`
- Source: user and build agent, session `ses_e2f1054caffewx6BpAMM7vhgNI`, through response `msg_1d108f840001P5LQ9WhcPmplnM`; [PR #11](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11)
- Related: [Mod and plugin metadata release versions](2026-11-12-metadata-release-versions.md), implemented at `f630b712ecccb859392b86bf799504de2c9d1977`.

## Decision and context

The user requested SemVer release tags with prerelease and build metadata support. Validate the complete tag for both mod and plugin ingestion before metadata or binary downloads, allowing one optional leading lowercase `v`. Apply the same complete parsing to supplied metadata versions; preserve prerelease and build identifiers when matching the tag. The previous metadata decision remains in force, including inference for missing mod versions and optional plugin versions.

Before this change, `Version.parse` alone was used. A new regression test showed it accepted a trailing newline: mod ingestion reached metadata download and plugin ingestion reached asset selection instead of rejecting the invalid tag. The agent chose to compare the parsed version's string with the entire input after removing one optional `v`. This rejects the observed edge case while retaining valid prerelease and build identifiers. The prior approach of relying on `Version.parse` alone was insufficient; no other alternatives or rationale are recorded.

## Consequences and evidence

[Version parsing](../src/zero_infra_mod_registry/utils/version_requirements.py) and [release retrieval](../src/zero_infra_mod_registry/retriever/github_mod_metadata_retriever.py) implement the change; [ingestion tests](../tests/test_release_metadata_assets.py) cover malformed tags and metadata versions, and the mod and plugin tests cover valid prerelease and build forms. The source transcript reports an initial test run with two newline failures, followed by 491 passed and four Docker-only skips, strict mypy on 65 files, and a generation check. These results were not rerun for this review. The transcript shows PR #11 open at `5bb906b342cd4d3bf42794064877518556d5d5e3`; its later status was not checked.

The standalone metadata validation action has no release tag for comparison, as noted in the earlier record. This decision concerns ingestion; it does not establish that every other version-parsing path uses the stricter helper. Reconsider if version syntax, validation boundaries, or matching policy change. Earlier discussions outside the supplied conversation and later developments are unavailable.

## Subsequent developments (2026-11-12)

The statement that metadata versions use the same optional-prefix parsing as release tags is superseded: supplied metadata must be unprefixed, while release tags still allow `v`. See [unprefixed metadata versions and launcher compatibility](2026-11-12-unprefixed-metadata-versions.md). Complete parsing and the remaining decision still apply.
