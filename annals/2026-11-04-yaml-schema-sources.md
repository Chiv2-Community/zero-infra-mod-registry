# YAML schema and OpenAPI sources

- Date: 2026-11-04
- Status: proposed; implementation uncommitted
- Scope: schema authoring, generated models, packaging and OpenAPI
- Repository: [zero-infra-mod-registry](https://github.com/Chiv2-Community/zero-infra-mod-registry)
- Branch: `feature/github-registry-openapi`
- HEAD at recording: `766e1df8c403eed867dd01d2a20fbf8b860268ab`; no exact tag. Nearest release baseline: `v1.1` and `v1` at `6af239ad50ef20c4f4106b2e47ca2bf9341ec6f8`.
- Source: user and build agent, session `ses_e5e1d6c8fffeDU7bqMVcEgIGoS`, through response `msg_1a8af3f1e001X1um77KXJlF0ty`; earlier history was compacted.
- Working tree: schema conversion, OpenAPI, generation, tests and documentation are uncommitted and not included in the recorded HEAD.

## Decision and context

At the user's request, replace the JSON authoring files with eight root `schemas/*.schema.yaml` files and [openapi.yaml](../openapi.yaml). JSON Schema 2020-12 remains the schema dialect; registry records, metadata, issue payloads and the model codec remain JSON. The [earlier OpenAPI proposal](2026-11-04-github-backed-openapi.md) referenced an uncommitted `openapi.json`; that filename is superseded, not its GitHub-backed routing design.

The previous committed schemas were JSON. The chosen conversion changes schema filenames, relative references and canonical IDs from `prepare-v1/schemas/*.schema.json` to `main/schemas/*.schema.yaml`. The reason for choosing YAML was the user's request; no further rationale or formal comparison with dual-format sources is recorded.

## Evidence and implementation

- The working tree contains [the YAML spec](../openapi.yaml), [schema sources](../schemas/), [loader](../packages/generated-models/src/generated_models/schema_documents.py), and [OpenAPI tests](../tests/test_openapi.py). The loader uses PyYAML; code generation and runtime schema loading use it. The build hook bundles root schemas in wheel and sdist artifacts without a checked-in consumer copy.
- The source transcript reports a parsed-value comparison of all eight schemas against the prior committed JSON documents, after replacing IDs and reference paths; it found no other differences. This review did not independently repeat the comparison.
- The transcript reports 416 tests passed and four optional Docker tests skipped, mypy passed for 67 files, and the generator check passed. Those commands were not rerun in this review.
- Prior tags contain the JSON schemas; direct schema links and tools must migrate to YAML. The new `main` IDs describe intended locations and are not evidence that uncommitted YAML is already published there.

## Consequences and reconsideration

Consumers of schema documents need YAML parsing, and generated-models gains a PyYAML runtime dependency. JSON wire compatibility is intended to remain unchanged. Reconsider if consumers cannot load YAML or external references, or if schema equivalence or packaging validation fails. No merge, release, or implementation commit is established; the transcript does not record other options considered or a more specific rationale.

## Subsequent developments (2026-11-04)

The uncommitted status and statement that no implementation commit was established are historical. Commit `f2d306002558c07905dfe8e61f942eb9a6698ecb` implements the conversion on an open PR branch; see the [implementation record](2026-11-04-openapi-yaml-pr-implementation.md). Merge is not established.
