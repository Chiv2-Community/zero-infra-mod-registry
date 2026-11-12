# Launcher main rejects plugin metadata version

- Date: 2026-11-12
- Status: accepted rollout constraint; compatibility fix not verified
- Scope: plugin registry metadata and UnchainedLauncher compatibility
- Repository: [Chiv2-Community/zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry); remote `https://github.com/Chiv2-Community/zero-infra-mod-registry.git`
- Branch: `feature/mod-json-version`; recording HEAD: `a994805a3e68cd63431b04b662b8314eca7df2aa`; exact tag: none; nearest tag: `v1`
- Source: user and build agent, session `ses_e2f1054caffewx6BpAMM7vhgNI`, through response `msg_1d10dba4a001n3OBKNX6Pv8kCO`; [PR #11](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11)
- Related: [unprefixed metadata versions and launcher compatibility](2026-11-12-unprefixed-metadata-versions.md).

## Finding and rollout constraint

The earlier record identified strict plugin deserialization in a modified local launcher checkout but did not attribute it to a released or remote branch. Subsequent source inspection establishes that launcher `origin/main` also has a strict `PluginInfo` with no `version` member. Publishing plugin registry metadata containing this field therefore requires coordinated launcher support before rollout to consumers of that branch. This narrows the earlier uncertainty; it does not refute its qualified claim. No implementation of the launcher fix or deployment schedule was established.

## Evidence and context

The user asked which branches had strict deserialization. The build agent fetched launcher refs and inspected them. This review independently inspected launcher `origin/main` at `93f89c847c89f6bdd06d733bb147792f63305fa8`: `UnchainedLauncher.Core/Services/Dlls/DllRelease.cs` applies `JsonUnmappedMemberHandling.Disallow` to `PluginInfo` and declares no version property. The strict behavior was introduced by launcher commit `c8bd89504e6f4a789456882b4ca6c97b1e8c577e`. The source response also reports it on `server-cli`, `feature/dll-validation`, and other feature and fix branches; branch names are time-sensitive. It reports absence on `hotfix/v1.0.x` and released v1.0.0 / RC4; the prior record describes the release-source evidence. No launcher runtime test was supplied or rerun.

The registry implementation adds an optional plugin version to stored plugin info; plugin metadata without it remains supported. The risk concerns records that actually contain the new field. The release-tag source of versions and mod compatibility are unchanged by this finding.

## Alternatives, follow-up and uncertainty

The source response calls for updating launcher main before publishing plugin versions; it does not record a comparison of alternative mitigations or an agreed release sequence. Confirm the fix in the actual launcher version and test deserialization against representative registry output before publishing. Reconsider this constraint when strict consumers support the field or a separately verified compatibility strategy is adopted. The transcript may omit earlier history; current PR and launcher deployment status were not independently checked.

## Subsequent developments (2026-11-12)

The earlier absence of a documented release sequence is now qualified by a proposed parallel implementation and rollout gate in launcher issue #183; implementation and deployment remain unverified. See [launcher plugin version compatibility follow-up](2026-11-12-launcher-version-follow-up.md).
