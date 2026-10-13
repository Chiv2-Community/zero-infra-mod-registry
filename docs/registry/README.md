# Registry setup

Create a GitHub repository with a `main` branch and enable Issues and Actions.
Enable **Settings → Actions → General → Allow GitHub Actions to create and approve
pull requests**. Maintainers still review and merge registration PRs. Register
dependencies before dependent releases.

The root action creates `registry/`, `package_db/`, and `dll_db/` on first
registration. Existing registries use the same directories. The validator also
reads legacy `dll_db/index.json` records.

## Process issues

The workflow reads the current issue body, registers one release, validates both
databases and DLL downloads, and opens a PR linked to the issue. Failures are
reported with a workflow-log link. Correct the request or release, then reply
`retry`. No registration commit is created on failure. Merging the PR closes the
issue. PR comments are ignored.

The workflow uses the caller's `GITHUB_TOKEN`; no additional secrets are required.

| Input | Example | Default | Description |
|---|---|---|---|
| `registry_branch` | `main` | `main` | Registry branch used as the registration PR base |
| `tool_ref` | `91583711a43d2ca53bf88e097d7a788165d9cf68` | `main` | Upstream implementation revision; pin to the same SHA as the workflow reference |

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

### Issue payload

Requests contain a fenced JSON block identifying one published release.

| Field | Example | Requirement | Description |
|---|---|---|---|
| `action` | `add-package-release` | Required | `add-package-release` for pak mods or `add-dll-release` for plugins |
| `repo_url` | `https://github.com/Owner/Mod` | Required | GitHub repository hosting the release |
| `release_tag` | `v1.0.0` | Required | Exact published release tag |
| `dll_file` | `Plugin.dll` | Required for multiple DLLs | Exact, case-sensitive DLL asset filename |

````text
```json
{
  "action": "add-package-release",
  "repo_url": "https://github.com/Owner/Mod",
  "release_tag": "v1.0.0"
}
```
````

## Validate pull requests

This checks the PR merge snapshot, dependencies, indexes and downloaded DLL
hashes/sizes. Require this check for human-created PRs. PRs created using
`GITHUB_TOKEN` do not trigger another workflow run; the issue workflow validates
them before opening the PR.

| Input | Example | Default | Description |
|---|---|---|---|
| `tool_ref` | `91583711a43d2ca53bf88e097d7a788165d9cf68` | `main` | Upstream implementation revision; pin to the same SHA as the workflow reference |

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

## Publish

Clients can read `main` directly. To maintain a separate consumer branch, use
[the publishing workflow](publishing.md). See [action inputs and CLI](actions.md)
for manual registry operations.

## Optional automated publishing

The registry works with manually opened registration issues. To automate them,
deploy [automated-registry-gateway](automated-registry-gateway.md) on an HTTPS
server and let publishers use `actions/automated-publish`. Both are optional.
The gateway authenticates publishers with GitHub OIDC and creates issues using
your GitHub App. The issue workflow above processes those requests unchanged.
