# Metadata models

Schemas are the source of truth. Dataclasses are generated at development time
and checked in. Do not edit generated Python or the bundled request-schema copy.

| Schema | Contract |
|---|---|
| `schemas/mod-metadata.schema.json` | Stored mod metadata, dependencies, and releases |
| `schemas/dll-metadata.schema.json` | Stored DLL metadata, packages, and resolved releases |
| `schemas/pak-manifest.schema.json` | Scanner inventories and pak assets |
| `schemas/request.schema.json` | Fenced registration requests in registry issues |
| `schemas/mod.schema.json`, `schemas/plugin.schema.json` | Submission validation |
| `schemas/registry.schema.json` | References to stored-record contracts |

Regenerate after changing schemas or generation templates:

```sh
uv sync --all-groups
uv run python scripts/generate_models.py
uv run python scripts/generate_models.py --check
```

CI checks regeneration, strict typing, and tests. The pinned generator and locked
formatters make generation reproducible. Runtime installs do not need the generator.

`models/generated.py` contains metadata dataclasses. Shared issue-request types
live in `mod_registry_core/generated_requests.py` so the gateway does not depend
on the registry application. The request schema is copied into that package by
the same generation command; the check also detects a stale copy.

Loading validates raw JSON with `jsonschema`, then structures it with `cattrs`.
Generated convenience methods delegate to handwritten loading, serialization,
and semantic-check functions; templates never duplicate field declarations.
Repository identity (`Repo`) is an internal helper, not a metadata document.

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
