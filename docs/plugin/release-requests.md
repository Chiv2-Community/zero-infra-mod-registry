# Automated publish (optional)

`actions/automated-publish` authenticates to `automated-registry-gateway` with
GitHub OIDC. The gateway verifies the published release and asset, then creates a
registry issue. Output: `issue_url`. Publishers need no custom secret.

For plugins, `asset_name` becomes `dll_file` in the request. Mod registration scans
the release's pak assets.

The action and gateway are optional. To register manually, open a registry issue
with the [release payload](../registry/README.md#issue-payload).

Reruns reuse open or closed issues for the same repository/tag. Serialize requests
with concurrency. Correct failures and reply `retry` on the issue. Maintainers
review and merge the generated approval PR.

Use your registry operator's HTTPS endpoint. Enable `id-token: write` on the job
and run it from the published tag. See [gateway deployment](../registry/automated-registry-gateway.md)
for server setup and enrollment. Public repositories are supported.

| Input | Example | Default | Description |
|---|---|---|---|
| `kind` | `plugin` | Required | `plugin` for DLLs or `mod` for pak assets |
| `endpoint` | `https://registry.example.com/registrations` | Empty | OIDC gateway URL; use this or `registry_token` |
| `release_tag` | `v1.0.0` | `github.ref_name` | Published semantic version tag; OIDC requires the workflow tag |
| `asset_name` | `Plugin.dll` | Empty | Exact asset filename; required for multiple DLLs |
| `registry_token` | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Empty | Direct mode only: token with Issues write access to the registry |
| `registry_repository` | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Direct mode only: destination owner/repository |
| `source_token` | `${{ secrets.GITHUB_TOKEN }}` | `github.token` | Direct mode only: token with read access to the release repository |
| `source_repository` | `Owner/Plugin` | `github.repository` | Direct mode: release owner/repository; OIDC uses the workflow repository |

Add this job after release publication. Use your publishing job name in `needs`.
No checkout is required.

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
        kind: plugin
        asset_name: Plugin.dll
```

## Direct token mode

Existing integrations can omit `endpoint` and provide `registry_token` instead.
The action verifies the release with `source_token` and creates the issue directly.
Configure a token with Issues write access to the destination registry and store
it as `REGISTRY_ISSUE_TOKEN`. Direct mode does not require `id-token: write`.

| Input | Example | Default | Description |
|---|---|---|---|
| `kind` | `plugin` | Required | DLL or pak registration |
| `registry_token` | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Empty | Required in direct mode; Issues write token |
| `asset_name` | `Plugin.dll` | Empty | Exact release asset filename |

```yaml
steps:
  - uses: Chiv2-Community/zero-infra-mod-registry/actions/automated-publish@prepare-v1
    with:
      kind: plugin
      asset_name: Plugin.dll
      registry_token: ${{ secrets.REGISTRY_ISSUE_TOKEN }}
```

## Errors

HTTP errors include a cause and next step. Check identity for `401`, tag for `403`,
asset for `422`, rate limits for `429`, and the server for `5xx`. Tokens and response
bodies stay out of errors. See the
[status table](../registry/automated-registry-gateway.md#operations-and-errors).
