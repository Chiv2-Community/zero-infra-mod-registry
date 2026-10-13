# Automated publish (optional)

`actions/automated-publish` authenticates to `automated-registry-gateway` with
GitHub OIDC. The gateway verifies the published release and asset, then creates a
registry issue. Output: `issue_url`. Publishers need no custom secret.

For plugins, `asset_name` becomes `dll_file` in the request. Mod registration scans
the release's pak assets.

The action and gateway are optional. To register manually, open a registry issue
with the [release payload](../registry/README.md#issue-payload).

Reruns reuse open or closed issues for the same repository/tag/kind. A different
DLL selection within that kind conflicts; this is not multi-DLL registration.
Serialize direct-mode requests for each repository/tag/kind with concurrency.
Correct failures and reply `retry` on the issue. Maintainers
review and merge the generated approval PR.

Use your registry operator's HTTPS endpoint. Enable `id-token: write` on the job
and run it from the published tag. See [gateway deployment](../registry/automated-registry-gateway.md)
for server setup and enrollment. Public repositories are supported.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `kind` | enum (`plugin`, `mod`) | Required | `plugin` | DLL or pak registration |
| `endpoint` | string | Empty | `https://registry.example.com/registrations` | OIDC gateway URL; use this or `registry_token` |
| `release_tag` | string | `github.ref_name` | `v1.0.0` | Published semantic version tag; OIDC requires the workflow tag |
| `asset_name` | string | Empty | `Plugin.dll` | Exact asset filename; required for multiple DLLs |
| `registry_token` | string | Empty | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Direct mode only: token with Issues write access to the registry |
| `registry_repository` | string | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Direct mode only: destination owner/repository |
| `source_token` | string | `github.token` | `${{ secrets.GITHUB_TOKEN }}` | Direct mode only: token with read access to the release repository |
| `source_repository` | string | `github.repository` | `Owner/Plugin` | Direct mode: release owner/repository; OIDC uses the workflow repository |

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

## Releases containing both a DLL and a PAK

Invoke the action twice, once per filename. This matrix runs two jobs, each with
its own OIDC identity. The release must still contain exactly one `.pak`; DLLs
do not count toward that limit. Each kind gets a separate issue and approval PR.

```yaml
request-registration:
  needs: publish-release
  runs-on: ubuntu-latest
  permissions:
    contents: read
    id-token: write
  strategy:
    fail-fast: false
    matrix:
      include:
        - kind: plugin
          asset: Plugin.dll
        - kind: mod
          asset: Mod.pak
  concurrency:
    group: registry-release-${{ github.repository }}-${{ github.ref }}-${{ matrix.kind }}
    cancel-in-progress: false
  steps:
    - uses: Chiv2-Community/zero-infra-mod-registry/actions/automated-publish@prepare-v1
      with:
        endpoint: https://registry.example.com/registrations
        kind: ${{ matrix.kind }}
        asset_name: ${{ matrix.asset }}
```

The action requests a token on every invocation, but the gateway never permits
the same token to create a second registration, even for another kind. If an
issuer reuses a job's token, use separate jobs as above; do not reuse a bearer
token manually. Direct mode can instead use two sequential action steps.

## Direct token mode

Existing integrations can omit `endpoint` and provide `registry_token` instead.
The action verifies the release with `source_token` and creates the issue directly.
Configure a token with Issues write access to the destination registry and store
it as `REGISTRY_ISSUE_TOKEN`. Direct mode does not require `id-token: write`.

| Input | Type | Default | Example | Description |
|---|---|---|---|---|
| `kind` | enum (`plugin`, `mod`) | Required | `plugin` | DLL or pak registration |
| `registry_token` | string | Empty | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Required in direct mode; Issues write token |
| `asset_name` | string | Empty | `Plugin.dll` | Exact release asset filename |

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
