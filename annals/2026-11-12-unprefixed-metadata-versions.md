# Unprefixed metadata versions and launcher compatibility

- Date: 2026-11-12
- Status: implemented on feature branch; PR open at source response
- Scope: mod and plugin metadata version spelling and launcher compatibility
- Repository: [Chiv2-Community/zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry); remote `https://github.com/Chiv2-Community/zero-infra-mod-registry.git`
- Branch: `feature/mod-json-version`; recording HEAD and implementation: `f0b290b3e31816d4ea36b05a9249104e9c2620d4`
- Exact HEAD tag: none; nearest reachable tag: `v1`
- Source: user and build agent, session `ses_e2f1054caffewx6BpAMM7vhgNI`, through response `msg_1d10c13790014pjfTKXAUg2Tfo`; [PR #11](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11)

## Decision and change

The user rejected optional `v` in metadata versions and requested stripping it when inferring from tags. Supplied `mod.json` and `plugin.json` versions must be complete, unprefixed SemVer and match the release tag after removing at most one leading lowercase `v`, including prerelease and build identifiers. Release tags themselves may still have that prefix. Missing mod versions continue to be inferred without it; missing plugin versions remain optional.

This supersedes only the allowance of prefixed metadata versions in [metadata release versions](2026-11-12-metadata-release-versions.md) and [complete SemVer release tags](2026-11-12-complete-semver-release-tags.md), not their other decisions. The earlier agent-supported alternative allowed `v` on either value; the user changed that policy. No further rationale was recorded.

## Evidence and consequences

Commit `f0b290b3e31816d4ea36b05a9249104e9c2620d4` separates [unprefixed parsing and release-tag parsing](../src/zero_infra_mod_registry/utils/version_requirements.py); [ingestion tests](../tests/test_release_metadata_assets.py) reject prefixed metadata. The input schemas describe strings; the ingestion helper enforces SemVer and matching. The separate metadata validation action does not compare a release tag. The transcript reports 473 tests passed, four Docker-only skips, mypy on 65 files and a generation check; this review did not rerun them. PR #11 was open at this commit in the transcript; present remote status was not independently checked.

The build agent inspected UnchainedLauncher tags `v1.0.0` (`b6171aa0a8dbf0695d879839f62832fb7fe733ca`) and `v1.0.0-RC4` (`c7775ab638fbdfa4dfa98b934a09350e5805f01b`): their mod model lacks the new field, derives versions from release tags, and their serializer does not configure unknown-member rejection. The agent reported neither release consumes plugin registry metadata. This is source-based compatibility evidence, not an end-to-end execution of either release. A newer local launcher checkout had strict plugin deserialization and may reject the added field; its working tree was modified, so this is not a claim about a particular released launcher. Coordinate support with strict plugin consumers before rollout.

## Reconsideration and gaps

Reconsider if metadata prefix policy changes, compatibility testing finds a regression, or strict consumers add support. The user's reason for preferring unprefixed metadata is not recorded. The supplied conversation may omit earlier history; no launcher runtime compatibility test was supplied or rerun.
