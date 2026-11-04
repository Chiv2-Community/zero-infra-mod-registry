# GitHub-backed registry OpenAPI contract

- Date: 2026-11-04
- Status: proposed; implementation uncommitted
- Scope: registry discovery, stored package metadata and release asset reads
- Repository: [zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry)
- Branch: `feature/github-registry-openapi`
- HEAD at recording: `6af239ad50ef20c4f4106b2e47ca2bf9341ec6f8`; exact tags `v1.1` and `v1`. Neither tag contains this uncommitted proposal.
- Source: user and build agent, session `ses_e5e1d6c8fffeDU7bqMVcEgIGoS`, through response `msg_1a8a84ebb001ebUJfUxv1mHGAx`. Earlier history was compacted.
- Working tree: the spec, documentation, tests and dependency changes are uncommitted; the annal does not commit them.

## Decision and context

The user requested an OpenAPI description based on UnchainedLauncher and the existing models, emphasizing that GitHub file and release locations provide the routes, not a registry server. The working proposal describes read-only discovery and downloads rather than inventing server endpoints. Root schemas remain authoritative; package JSON references the stored pak and DLL package schemas rather than resolved DLL runtime objects.

Registry indexes and package files use the raw GitHub metadata server. Publisher release GET and HEAD operations each explicitly override that server to `https://github.com`, with independent publisher owner and repository parameters. After the user observed that the original server layout could suggest assets lived in the registry repository, the agent moved the existing path-level override to both operations and added an illustrative cross-repository test. This is a clarification of the representation, not evidence that the prior path-level override actually routed to the registry repository.

## Evidence and options

- The [draft spec](../openapi.json), [explanation](../docs/openapi.md), and [tests](../tests/test_openapi.py) show the uncommitted design. Launcher references in the explanation pin source to `5bd94fcdb33035e6eb624c71244e70c17b68a1a9`.
- The source transcript reports `text/plain` responses to two live GitHub HEAD requests and a pinned C2ModRegistry snapshot at `1d3c56e3cbc85e7406b5a361831e1da3ad8f2da0`. Tests cover 19 pak and one DLL package, offline schema resolution, and publisher GET/HEAD server selection.
- The initial full suite reported 414 passed and four skipped before the final server clarification; after it, focused OpenAPI/type-contract tests reported seven passed and mypy passed. This review did not rerun those checks.
- A path-level publisher server override was implemented first; operation-level overrides were chosen for clarity after the user's concern. A fabricated registry server, copied schemas, and using resolved DLL models as stored wire schemas would conflict with the stated contract; no evidence establishes a formal comparison of those alternatives.

## Consequences and follow-up

The spec documents plain-text indexes, JSON parsed from raw text, publisher assets, redirects, and integrity guidance. GitHub controls availability and HTTP behavior; moving branches and caches do not provide transactional multi-file reads. The draft excludes the legacy flat DLL index, registration workflows, and the optional gateway from this read/download scope. It requires schemas alongside the spec and needs review for tool interoperability and any future changes in launcher or GitHub behavior.

The tests preserve OpenAPI components at their reference URI and embed full schema documents under file-URI aliases: fragment pointers failed when wrappers or aliases lacked the referenced content. This is a test-resolution choice, not a change to the authoritative schemas.

## Release provenance and open questions

Before this worktree was created, the user authorized merging [PR #9](https://github.com/Chiv2-Community/zero-infra-mod-registry/pull/9) and publishing `v1.1` while moving `v1`. The source transcript records merge commit `6af239ad50ef20c4f4106b2e47ca2bf9341ec6f8`, reviewed PR head `64609a4908522a580a4085abac98f3a25d262a2a`, and remote verification that both annotated tags peeled to the merge. Local Git confirms both tags point there. Image publication was still running in the transcript; its final result is unknown here.

No approval, commit, PR, or release of the OpenAPI proposal is established. Reconsider scope and server representation if launcher discovery changes, a registry HTTP service is introduced, or OpenAPI consumers cannot resolve the external schemas. The compacted conversation may omit earlier rationale and alternatives.
