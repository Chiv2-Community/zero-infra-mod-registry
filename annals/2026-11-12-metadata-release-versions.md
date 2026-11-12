# Mod and plugin metadata release versions

- Date: 2026-11-12
- Status: implemented on feature branch; PR pending at source response
- Scope: mod and plugin release ingestion and stored metadata
- Repository: [Chiv2-Community/zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry)
- Branch: `feature/mod-json-version`
- Recording HEAD and implementation: `f630b712ecccb859392b86bf799504de2c9d1977`; base: `6af239ad50ef20c4f4106b2e47ca2bf9341ec6f8`
- Exact HEAD tag: none; nearest reachable tag: `v1`
- Source: user and build agent, session `ses_e2f1054caffewx6BpAMM7vhgNI`, through response `msg_1d0f50eb7001Z6Intg3IgEpHz0`; [PR #11](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11)

## Decision and context

Preserve optional metadata `version` fields in generated mod and plugin models. On release ingestion, a supplied version must match the release tag after removing an optional leading lowercase `v` and parsing both as SemVer; prerelease and build identifiers must match. Preserve the supplied spelling. Continue to use release tags for ordering and dependency resolution. The user requested the match for both kinds, then explicitly requested inference when `mod.json` omits the version.

For a newly ingested mod with no version, derive it from the parsed tag without its leading `v`. For a plugin with no version, leave it absent. Stored models remain nullable for older registry records. Ingestion checks before downloading the binary; the separate metadata validation action has no release tag to compare. Schema files define the input and stored data shapes; registry packages store JSON data, not schema files.

## Evolution, rationale and tradeoffs

The initial agent implementation preserved an optional mod string without matching the tag, to avoid breaking old metadata. The user changed that plan to require matching for mods and plugins; the user then replaced the initial missing-mod null behavior with tag inference. Plugin omission remains supported, an agent choice for compatibility rather than an explicit inference request. No other alternatives or rationale were recorded. The optional stored representation supports older records, but does not itself enforce cross-field matching when loading stored packages.

The input schemas describe strings; semantic validation and tag comparison occur in the retriever, not in the standalone schema check. Explicit differing build identifiers are rejected even though SemVer precedence normally ignores build metadata. Existing stored records are not retroactively populated by this ingestion path. Reconsider if consumers need retroactive migration, plugin inference, or a different matching policy.

## Evidence and status

Commit `f630b712ecccb859392b86bf799504de2c9d1977` changes the schemas, generated models, retriever, version helper, docs and tests. See [matching helper](../src/zero_infra_mod_registry/utils/version_requirements.py), [retriever](../src/zero_infra_mod_registry/retriever/github_mod_metadata_retriever.py), and [ingestion tests](../tests/test_release_metadata_assets.py). Tests cover mismatches before download, both metadata sources, round trips, and inferred mod versions.

The source transcript reports 427 tests passed and four skipped, mypy passed on 65 files, and generation check passed. These are transcripted tool results, not rerun during this review. It also shows PR #11 open at the implementation commit; subsequent PR state was not checked. The supplied transcript is the available history; earlier discussions and any later changes are unknown.

## Subsequent developments (2026-11-12)

The ingestion parsing described above was strengthened to reject incomplete SemVer input before metadata downloads. The decision itself remains in force. See [complete SemVer release tags](2026-11-12-complete-semver-release-tags.md).

### Subsequent developments (2026-11-12): metadata prefix

The allowance in the decision for a leading `v` on supplied metadata versions is superseded; release tags may retain it. See [unprefixed metadata versions and launcher compatibility](2026-11-12-unprefixed-metadata-versions.md). The rest of this decision remains in force.
