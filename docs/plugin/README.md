# Plugin integration

1. Add [`plugin.json`](../../schemas/plugin.schema.json) at the repository root.
   Include `name`, `description`, `authors`, `plugin_dependencies` and
   `mod_dependencies`. Set `target` to `server`, `client`, or `shared` (default).
2. Validate metadata before publishing.
3. Tag a semantic version release and upload the DLL. A release-asset
   `plugin.json` overrides metadata committed at the tag.
4. Open a registration issue manually or use [automated publish](release-requests.md).
   The automated action and gateway are optional. Each version requires registry
   maintainer approval. Publish a new version when DLL contents change.

## Metadata workflow

The action checks metadata schemas and dependency versions against the registry.
Make your release build depend on this job to block publication when metadata is
invalid. Use Linux runners and register dependencies first.

The action installs Python through uv and reads dependency records from a
checkout at `.metadata-validation-registry`. It fails if neither metadata file
exists.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `plugin_file` | string | Auto-detect root `plugin.json` | `plugin.json` | Plugin metadata path |
| `mod_file` | string | Auto-detect root `mod.json` | `mod.json` | Pak metadata path; also validated when present |
| `registry_repository` | string | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Dependency registry owner/repository |
| `registry_ref` | string | `main` | `main` | Registry branch, tag or commit SHA |
| `registry_token` | string | `github.token` | `${{ secrets.REGISTRY_READ_TOKEN }}` | Read access token; supply one for private registries |

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
