# Plugin integration

1. Add [`plugin.json`](../../schemas/plugin.schema.json) at the repository root.
   Include `name`, `description`, `authors`, `plugin_dependencies` and
   `mod_dependencies`. Set `target` to `server`, `client`, or `shared` (default).
2. Validate metadata before publishing.
3. Tag a semantic version release and upload the DLL. A release-asset
   `plugin.json` overrides metadata committed at the tag.
4. [Request registration](release-requests.md). Each version requires registry
   maintainer approval. Publish a new version when DLL contents change.

## Metadata workflow

Save as `.github/workflows/metadata.yml`:

```yaml
name: Validate plugin metadata
on: [push, pull_request]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Chiv2-Community/zero-infra-mod-registry/actions/validate-metadata@main
        with:
          plugin_file: plugin.json
```

The action checks the schema and dependency versions against the registry. It
does not download release assets. Make your release build depend on this job to
block publication when metadata is invalid.

| Input | Default | Usage |
|---|---|---|
| `plugin_file` | Auto-detect root `plugin.json` | Explicit plugin metadata path |
| `mod_file` | Auto-detect root `mod.json` | Also validate pak metadata when present |
| `registry_repository` | `Chiv2-Community/C2ModRegistry` | Dependency registry |
| `registry_ref` | `main` | Registry branch, tag or SHA |
| `registry_token` | `github.token` | Read access; provide a token for private registries |

The action fails if neither metadata file exists. It installs Python through uv
and reads dependency records from a checkout at `.metadata-validation-registry`.
Use Linux runners. Register dependencies before publishing dependent plugins.
