# Publish a consumer branch

The workflow checks out and validates an approved snapshot, including DLL
downloads, then merges it into the destination branch. Conflicts and
non-fast-forward push races fail without forcing changes. Repeated delivery is
a no-op. This publishes the full Git tree.

Create the destination branch from the source branch once. Repository rules must
permit the Actions token to push to it. Use a separate caller and concurrency
group for each destination, including temporary compatibility branches.

The event must run from the source branch. Pin both the workflow reference and
`tool_ref` to the same commit for reproducibility.

| Input | Example | Default | Description |
|---|---|---|---|
| `target_branch` | `db` | Required | Existing destination branch |
| `source_branch` | `main` | `main` | Branch containing the approved registry |
| `source_sha` | `${{ github.sha }}` | Event SHA | Full 40-character commit SHA reachable from the source branch |
| `tool_ref` | `91583711a43d2ca53bf88e097d7a788165d9cf68` | `main` | Upstream implementation branch, tag or commit |

Save this workflow in the registry:

```yaml
name: Publish registry
on:
  push:
    branches: [main]
permissions:
  contents: write
concurrency:
  group: publish-db
  cancel-in-progress: false
jobs:
  publish:
    uses: Chiv2-Community/zero-infra-mod-registry/.github/workflows/publish-registry.yml@main
    with:
      target_branch: db
      tool_ref: main
```

## Branch action

`actions/publish-branch` provides only the merge operation. For custom workflows,
checkout with `fetch-depth: 0` and validate the source snapshot first. The
checked-out HEAD must equal `source_sha`. Git credentials must already allow
pushing. Use the reusable workflow to include validation automatically.

| Input | Example | Default | Description |
|---|---|---|---|
| `target_branch` | `db` | Required | Existing destination branch |
| `source_branch` | `main` | `main` | Approved source branch; must match the event branch |
| `source_sha` | `${{ github.sha }}` | Required | Full 40-character source commit SHA; must match HEAD and be reachable from the source branch |

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
  - uses: Chiv2-Community/zero-infra-mod-registry@main
    with:
      command: validate
      verify_dll_downloads: 'true'
  - uses: Chiv2-Community/zero-infra-mod-registry/actions/publish-branch@main
    with:
      source_sha: ${{ github.sha }}
      target_branch: db
```
