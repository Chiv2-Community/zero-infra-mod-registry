# Launcher plugin version compatibility follow-up

- Date: 2026-11-12
- Status: proposed; issue open at review
- Scope: launcher compatibility and registry rollout sequencing
- Repository: [zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry); remote `https://github.com/Chiv2-Community/zero-infra-mod-registry.git`
- Branch: `feature/mod-json-version`; recording HEAD: `2a63e2c153e2c909cde29f2c4ec007f2d6939025`; exact tag: none; nearest tag: `v1`
- Source: user and build agent, session `ses_e2f1054caffewx6BpAMM7vhgNI`, through response `msg_1d11505cd001oFaekYSuLn1T9b`; [registry PR #11](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11).

## Decision and evidence

The user requested an issue to fix the strict plugin deserialization incompatibility on launcher main. [UnchainedLauncher #183](https://github.com/Chiv2-Community/UnchainedLauncher/issues/183) was created and remains open at this review. It links PR #11; the agent also linked the issue from [the PR](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/11#issuecomment-6832756131).

The [prior compatibility record](2026-11-12-launcher-main-plugin-compatibility.md) established that launcher main at `93f89c847c89f6bdd06d733bb147792f63305fa8` has a strict `PluginInfo` without `version`. The issue proposes explicit nullable version support without relaxing unrelated strict validation. It covers package and legacy index/cache parsing, round trips, latest-release consistency, unprefixed SemVer matching including prerelease and build identifiers, and compatibility with missing metadata. These are issue acceptance criteria, not a verified implementation or an independently accepted launcher design.

## Sequencing and consequences

The issue and PR comment propose implementing launcher support in parallel with the registry PR, then landing and distributing it before publishing version-bearing plugin records to affected launcher clients. This makes the earlier rollout constraint actionable; it does not establish a deployment schedule or that the fix has shipped. General unknown-field tolerance and a v1.0.x backport are outside the issue scope; no comparative alternatives or rationale for those exclusions were recorded.

Reconsider the rollout gate after representative package and cache tests pass on the launcher version actually deployed, or a different compatibility strategy is verified. This review verified the issue's current title, body and open state, but did not run launcher tests or independently verify deployment. The supplied conversation may omit earlier history.
