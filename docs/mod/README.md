# Mod integration

1. Add [`mod.json`](../../schemas/mod.schema.json) at the repository root. Include
   name, description, authors and dependency declarations required by the schema.
2. Validate metadata before publishing.
3. Tag a semantic version release and upload the `.pak` asset. A release-asset
   `mod.json` overrides metadata committed at the tag. The registry scans pak
   assets to generate manifests.
4. Request registration after publishing. Each release requires approval.

## Metadata workflow

The action validates metadata schemas and registered dependency versions. Make
the publishing job depend on validation. For all options, see the
[metadata action inputs](../plugin/README.md#metadata-workflow).

| Input | Example | Default | Description |
|---|---|---|---|
| `mod_file` | `mod.json` | Auto-detect root `mod.json` | Pak metadata path |
| `registry_repository` | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Dependency registry owner/repository |
| `registry_ref` | `main` | `main` | Registry branch, tag or commit SHA |

Save as `.github/workflows/metadata.yml`:

```yaml
name: Validate mod metadata
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
          mod_file: mod.json
```

## Release request

The action checks the published pak asset and opens or reuses a registry issue.
Registry processing creates an approval PR. Configure `REGISTRY_ISSUE_TOKEN` with
Issues write access to the registry. See [all release-request inputs and retry
behavior](../plugin/release-requests.md).

| Input | Example | Default | Description |
|---|---|---|---|
| `kind` | `mod` | Required | Select pak registration |
| `registry_token` | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Required | Token with Issues write access to the registry |
| `release_tag` | `v1.0.0` | `github.ref_name` | Exact published semantic version tag |

Add this job to your release workflow. Use your publishing job name in `needs`:

```yaml
request-registration:
  needs: publish-release
  runs-on: ubuntu-latest
  permissions:
    contents: read
  concurrency:
    group: registry-release-${{ github.ref }}
    cancel-in-progress: false
  steps:
    - uses: Chiv2-Community/zero-infra-mod-registry/actions/request-release@main
      with:
        kind: mod
        registry_token: ${{ secrets.REGISTRY_ISSUE_TOKEN }}
```

For manual requests, use the [registry issue payload](../registry/README.md#issue-payload).
