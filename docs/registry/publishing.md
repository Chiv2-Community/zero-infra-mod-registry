# Publish a consumer branch

The workflow checks out and validates an approved snapshot, including DLL
downloads, then merges it into the destination branch and validates that exact
candidate before pushing. Conflicts, invalid merged registries and
non-fast-forward push races fail without forcing changes. Repeated delivery is
a no-op. This publishes the full Git tree.

Create the destination branch from the source branch once. Repository rules must
permit the Actions token to push to it. Use a separate caller and concurrency
group for each destination, including temporary compatibility branches.

The event must run from the source branch. Pin both the workflow reference and
`tool_ref` to the same commit for reproducibility.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `target_branch` | string | Required | `db` | Existing destination branch |
| `source_branch` | string | `main` | `main` | Branch containing the approved registry |
| `source_sha` | string | Event SHA | `${{ github.sha }}` | Full 40-character commit SHA reachable from the source branch |
| `tool_ref` | string | `main` | `91583711a43d2ca53bf88e097d7a788165d9cf68` | Upstream implementation branch, tag or commit |

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

`actions/publish-branch` prepares the merge without pushing and returns
`candidate_sha`. Custom workflows must validate both source and merged candidate,
then call `push.sh` with that SHA. Use the reusable workflow for these gates and
non-force publication. Checkout with `fetch-depth: 0`; HEAD must equal
`source_sha` before preparation. Git credentials must already allow pushing.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `target_branch` | string | Required | `db` | Existing destination branch |
| `source_branch` | string | `main` | `main` | Approved source branch; must match the event branch |
| `source_sha` | string | Required | `${{ github.sha }}` | Full 40-character source commit SHA; must match HEAD and be reachable from the source branch |

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
  - uses: Chiv2-Community/zero-infra-mod-registry@main
    with:
      command: validate
      verify_dll_downloads: 'true'
  - uses: actions/checkout@v4
    with:
      repository: Chiv2-Community/zero-infra-mod-registry
      path: .registry-tool
      persist-credentials: false
  - id: merge
    uses: ./.registry-tool/actions/publish-branch
    with:
      source_sha: ${{ github.sha }}
      target_branch: db
  - uses: ./.registry-tool
    with:
      command: validate
      verify_dll_downloads: 'true'
  - shell: bash
    env:
      CANDIDATE_SHA: ${{ steps.merge.outputs.candidate_sha }}
      TARGET_BRANCH: db
    run: bash .registry-tool/actions/publish-branch/push.sh
```
