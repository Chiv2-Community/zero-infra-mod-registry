# Metadata models

Schemas are the source of truth. Dataclasses are generated at development time
and checked in. Do not edit generated Python.

| Schema | Contract |
|---|---|
| `schemas/mod-metadata.schema.json` | Stored mod metadata, dependencies, and releases |
| `schemas/dll-metadata.schema.json` | Stored DLL metadata, packages, and resolved releases |
| `schemas/pak-manifest.schema.json` | Scanner inventories and pak assets |
| `schemas/request.schema.json` | Fenced registration requests in registry issues |
| `schemas/mod.schema.json` | Mod submission validation |
| `schemas/plugin.schema.json` | Plugin submission validation |
| `schemas/registry.schema.json` | References to stored-record contracts |

Regenerate after changing schemas or generation templates:

```sh
uv sync --all-groups
uv run python scripts/generate_models.py
uv run python scripts/generate_models.py --check
```

CI checks regeneration, strict typing, and tests. The pinned generator and locked
formatters make generation reproducible. Runtime installs do not need the generator.

`models/generated.py` contains metadata dataclasses. Dependency contracts share
the generated `models/generated_dependencies.py` value type; their URL and version
constraints are still checked against the applicable schema. Shared issue-request types
live in `mod_registry_core/generated_requests.py` so the gateway does not depend
on the registry application. Both applications use `schemas/request.schema.json`.
Package builds bundle that source automatically; no duplicate schema is checked in.
Both image builds include the root schemas directory in their build inputs.

Loading validates raw JSON with `jsonschema`, then structures it with `cattrs`.
Generated convenience methods delegate to handwritten loading, serialization,
and semantic-check functions; templates never duplicate field declarations.
Repository identity (`Repo`) is an internal helper, not a metadata document.

Plugin schemas enforce enums, nonblank text, authors, HTTPS media URLs, and
dependency URL patterns. Python checks case-insensitive repository uniqueness,
parses version requirements, and checks repository/tag consistency and registered
dependencies.

## Compatibility

Both `dependencies` and `mod_dependencies` are modeled. `dependencies` is
deprecated; `mod_dependencies` is required when `dependencies` is absent.
Declare an empty list when there are no pak dependencies.

`models/loading.py` normalizes both input lists into `mod_dependencies`,
deduplicating case-insensitive repository/version pairs. It clears the consumed
deprecated field. Serialization emits the merged list under both names, including
in historical releases. This behavior is not implemented in generated definitions.

Stored release timestamps accept timezone-naive ISO values as well as aware
values. The generation-only `x-python-datetime` annotation selects Python's
`datetime`; validation does not impose RFC 3339 on existing records.
