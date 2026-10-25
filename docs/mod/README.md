# Mod integration

1. Add [`mod.json`](../../schemas/mod.schema.json) at the repository root. Include
   name, description, authors and dependency declarations required by the schema.
2. Validate metadata before publishing.
3. Tag a semantic version release and upload the `.pak` asset. A release-asset
   `mod.json` overrides metadata committed at the tag. The registry scans pak
   assets to generate manifests.
4. Request registration after publishing. Each release requires approval.

## Dependencies and backward compatibility

Use `mod_dependencies` for pak mods and `plugin_dependencies` for DLL plugins.
`mod.json` also accepts `dependencies`, a deprecated alias of `mod_dependencies`.
If both are present, their lists are combined, deduplicating repository/version
pairs case-insensitively by repository URL.

Serialized pak releases and `latest_release_info` include both `mod_dependencies`
and an identical `dependencies` list for older clients, including when empty.
`plugin_dependencies` remain separate; they are never copied to `dependencies`.
Existing registry files receive the alias when rewritten, not by validation alone.

## Metadata workflow

The action validates metadata schemas and registered dependency versions. Make
the publishing job depend on validation. For all options, see the
[metadata action inputs](../plugin/README.md#metadata-workflow).

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `mod_file` | string | Auto-detect root `mod.json` | `mod.json` | Pak metadata path |
| `registry_repository` | string | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Dependency registry owner/repository |
| `registry_ref` | string | `main` | `main` | Registry branch, tag or commit SHA |

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

## Automated publish (optional)

The action authenticates to your registry's gateway using GitHub OIDC. The gateway
checks the published pak asset and opens or reuses a registry issue. Registry
processing creates an approval PR. No custom publisher secret is required. See
[all release-request inputs and retry behavior](../plugin/release-requests.md).

This action and `automated-registry-gateway` are optional. Publishers can open
registration issues manually instead.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `kind` | enum (`plugin`, `mod`) | Required | `mod` | Select pak registration |
| `endpoint` | string | Empty | `https://registry.example.com/registrations` | Your registry's HTTPS gateway URL |
| `release_tag` | string | `github.ref_name` | `v1.0.0` | Published semantic version tag; must match the workflow tag |

Add this job to your release workflow. Use your publishing job name in `needs`:

```yaml
request-registration:
  needs: publish-release
  runs-on: ubuntu-latest
  permissions:
    contents: read
    id-token: write
  concurrency:
    group: registry-release-${{ github.ref }}
    cancel-in-progress: false
  steps:
    - uses: Chiv2-Community/zero-infra-mod-registry/actions/automated-publish@prepare-v1
      with:
        endpoint: https://registry.example.com/registrations
        kind: mod
```

For manual requests, use the [registry issue payload](../registry/README.md#issue-payload).
