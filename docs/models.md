# Metadata models

YAML schemas are the source of truth; the dialect remains JSON Schema 2020-12.
Metadata, registry records and issue payloads remain JSON.
Dataclasses, schema bindings, and loading hooks
are generated at development time and checked in. Do not edit generated Python.

| Schema | Contract |
|---|---|
| `schemas/mod-metadata.schema.yaml` | Stored mod metadata, dependencies, and releases |
| `schemas/dll-metadata.schema.yaml` | Stored DLL metadata, packages, and resolved releases |
| `schemas/pak-manifest.schema.yaml` | Scanner inventories and pak assets |
| `schemas/request.schema.yaml` | Fenced registration requests in registry issues |
| `schemas/mod.schema.yaml` | Mod submission validation |
| `schemas/plugin.schema.yaml` | Plugin submission validation |
| `schemas/registry.schema.yaml` | References to stored-record contracts |

Run from the repository root after changing schemas or generator options:

```sh
uv sync --all-groups
uv run python -m code_gen
uv run python -m code_gen --check
```

CI checks regeneration, strict typing, and tests. The pinned generator and locked
formatters make generation reproducible. Runtime installs do not need the generator.

The independent `generated-models` workspace package contains `generated_models.metadata`,
`generated_models.dependencies`, `generated_models.requests`, `generated_models.json_types`,
and `generated_models.loading`.
Runtime dependencies are `jsonschema`, `cattrs`, and `PyYAML`. Consumers import its dataclasses and enums directly. Dependency contracts
share one value type; URL and version constraints remain in the applicable schemas.
Both applications use the generated loader for issue requests.
The generated-models build bundles root schemas automatically; consumers do not
carry separate schema copies. No duplicate schema is checked in.
Both image builds include the root schemas directory in their build inputs.
Schemas now use `.schema.yaml` filenames and canonical IDs under `main/schemas/`.
The earlier JSON schemas remain available at earlier Git tags; update direct
schema links when adopting this version. Tooling must parse YAML before JSON
Schema validation; this does not add YAML payload support to the model codec.

Loading validates raw JSON with `jsonschema`, then structures it with `cattrs`.
`generated_models.loading.load` validates before structuring; `serialize` applies
the generated wire transformations, including inside nested models.
The generated codec also owns JSON text decoding/encoding and schema-annotated
diagnostic context. The registry only configures semantic callbacks and package
adapters; adapters retain runtime repository identity and release selection.
The development-only `code-gen` package calls
the generator's Python API in-process and bundles local references for offline generation.
Repository identity (`Repo`) is an internal helper, not a metadata document.

## Consumer API

Install `generated-models` without either application or the generator. It owns
the shared `JsonValue`/`JsonObject` types and strict JSON boundary helpers; Python's
`json` module does not provide those recursive types or typed narrowing helpers.

```python
from generated_models.loading import dumps, loads
from generated_models.requests import RegistrationRequest

request = loads('{"action":"add-dll-release","repo_url":"https://github.com/Test/Plugin","release_tag":"v1.0.0"}', RegistrationRequest)
text = dumps(request, indent=2)
```

Use `load`/`serialize` for decoded JSON objects and `loads`/`dumps` for JSON text.
Text decoding rejects non-JSON constants (`NaN`, `Infinity`); encoding also rejects
non-finite numbers. Both APIs apply the same model transformations.

Consumers can create a `JsonCodec` and call `register_validator(Model, callback)`
for semantic checks or `register_serializer(Model, callback)` for domain adapters.
Callbacks apply to nested models, including after the codec's first use. They do
not affect other codec instances or the default module-level codec. Structural
schema validation runs before semantic callbacks. Generated code never imports
consumer modules.

`PluginPackage`/`PluginRelease` model stored DLL JSON. `Plugin`/`DllRelease` model
resolved releases with repository identity. The registry's domain adapters select
latest metadata and project resolved releases into the stored package shape.

Plugin schemas enforce enums, nonblank text, authors, HTTPS media URLs, and
dependency URL patterns. Python checks case-insensitive repository uniqueness,
parses version requirements, and checks repository/tag consistency and registered
dependencies.

## Compatibility

Both `dependencies` and `mod_dependencies` are modeled. `dependencies` is
deprecated; `mod_dependencies` is required when `dependencies` is absent.
Declare an empty list when there are no pak dependencies.

Generated loading normalizes both input lists into `mod_dependencies`,
deduplicating case-insensitive repository/version pairs. It clears the consumed
deprecated field. Serialization emits the merged list under both names, including
in historical releases. These hooks are derived from schema annotations.

| Annotation | Generated behavior |
|---|---|
| `x-python-name` | Map a wire field to its Python name in both directions |
| `x-python-null-as-default` | Replace an accepted null with the declared default |
| `x-python-merge-into` | Merge a deprecated list into its canonical field; clear the deprecated field on load |
| `x-python-unique-key` / `x-python-case-insensitive` | Select merge identity fields and case-insensitive comparisons |
| `x-python-serialize-alias` | Emit the merged list under the deprecated spelling too |
| `x-python-omit-none` | Omit null fields when serializing this model |
| `x-python-omit-empty` | Omit an empty field when serializing |
| `x-python-error-context` | Add a label and identifying field to model-structuring errors |

Annotations describe transformations, not additional validation constraints.
Raw input is always validated before normalization. SemVer interpretation,
dependency uniqueness and resolution, repository/tag consistency, release selection,
and downloaded-file integrity remain runtime checks.

Stored release timestamps accept timezone-naive ISO values as well as aware
values. The generation-only `x-python-datetime` annotation selects Python's
`datetime`; validation does not impose RFC 3339 on existing records.
