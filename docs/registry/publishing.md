# Publish a consumer branch

Create the destination branch from `main` once. Save this workflow in the registry:

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

Inputs: `target_branch` (required), `source_branch` (default `main`), `source_sha`
(default the event SHA), `tool_ref` (default `main`). The event must run from the
source branch. `source_sha` must be a full 40-character commit SHA reachable from
that branch. Pin both the workflow reference and `tool_ref` for reproducibility.

The workflow checks out and validates that exact snapshot, including DLL
downloads, then merges it into the destination. Conflicts and non-fast-forward
push races fail without forcing changes. Repeated delivery is a no-op. Repository
rules must permit the Actions token to push to the destination branch.

Use a separate caller and concurrency group for each destination, including
temporary compatibility branches. This publishes the full Git tree.

## Branch action

`actions/publish-branch` provides only the merge operation. For custom workflows,
checkout with `fetch-depth: 0`, validate the source snapshot, then call it with
`source_branch`, `source_sha`, and `target_branch`. The checked-out HEAD must equal
`source_sha`. Git credentials must already allow pushing. Use the reusable
workflow to include validation automatically.
