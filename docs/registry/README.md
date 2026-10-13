# Registry setup

Create a GitHub repository with a `main` branch and enable Issues and Actions.
Enable **Settings → Actions → General → Allow GitHub Actions to create and approve
pull requests**. Maintainers still review and merge registration PRs. Register
dependencies before dependent releases.

The root action creates `registry/`, `package_db/`, and `dll_db/` on first
registration. Existing registries use the same directories. The validator also
reads legacy `dll_db/index.json` records.

## Process issues

Save as `.github/workflows/register.yml`:

```yaml
name: Register release
on:
  issues:
    types: [opened]
  issue_comment:
    types: [created]
permissions:
  contents: write
  issues: write
  pull-requests: write
concurrency:
  group: registration-${{ github.event.issue.number }}
  cancel-in-progress: false
jobs:
  register:
    uses: Chiv2-Community/zero-infra-mod-registry/.github/workflows/register-release.yml@main
    with:
      registry_branch: main
      tool_ref: main
```

Requests contain a fenced JSON block:

````text
```json
{
  "action": "add-package-release",
  "repo_url": "https://github.com/Owner/Mod",
  "release_tag": "v1.0.0"
}
```
````

For plugins, use `add-dll-release`. If a release has multiple DLLs, include
`"dll_file": "Plugin.dll"` with the exact, case-sensitive asset filename.

The workflow reads the current issue body, registers one release, validates both
databases and DLL downloads, and opens a PR linked to the issue. Failures are
reported with a workflow-log link. Correct the request or release, then reply
`retry`. No registration commit is created on failure. Merging the PR closes the
issue. PR comments are ignored.

Inputs: `registry_branch` (default `main`), `tool_ref` (default `main`). The workflow
uses the caller's `GITHUB_TOKEN`; no additional secrets are required.

## Validate pull requests

Save as `.github/workflows/validate.yml`:

```yaml
name: Validate registry
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  validate:
    uses: Chiv2-Community/zero-infra-mod-registry/.github/workflows/validate-registry.yml@main
    with:
      tool_ref: main
```

This checks the PR merge snapshot, dependencies, indexes and downloaded DLL
hashes/sizes. Only `tool_ref` is configurable. Require this check for human-created
PRs. PRs created using `GITHUB_TOKEN` do not trigger another workflow run; the issue
workflow validates them before opening the PR.

## Publish

Clients can read `main` directly. To maintain a separate consumer branch, use
[the publishing workflow](publishing.md). See [action inputs and CLI](actions.md)
for manual registry operations.
