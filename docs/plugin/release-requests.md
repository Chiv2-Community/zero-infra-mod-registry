# Request release registration

`actions/request-release` verifies a published release and an uploaded, nonempty
asset, then creates a registration issue. For plugins, `asset_name` becomes
`dll_file` in the request. For mods, registration scans the release's pak assets.
Output: `issue_url`.

Reruns reuse an existing open or closed issue identified by repository and tag.
Serialize requests for the same repository/tag using concurrency. Correct failed
requests or releases and reply `retry` on the issue. Registration opens an
approval PR; maintainers merge it.

Create a fine-grained token with **Issues: write** access to the destination registry and
store it as `REGISTRY_ISSUE_TOKEN` in the publisher repository. The publisher's
`GITHUB_TOKEN` is scoped to its own repository; use the separate token for the
registry issue.

| Input | Example | Default | Description |
|---|---|---|---|
| `kind` | `plugin` | Required | `plugin` for DLLs or `mod` for pak assets |
| `registry_token` | `${{ secrets.REGISTRY_ISSUE_TOKEN }}` | Required | Token with Issues write access to the registry |
| `registry_repository` | `Chiv2-Community/C2ModRegistry` | `Chiv2-Community/C2ModRegistry` | Destination owner/repository |
| `source_token` | `${{ secrets.GITHUB_TOKEN }}` | `github.token` | Token with read access to the release repository |
| `source_repository` | `Owner/Plugin` | `github.repository` | Release owner/repository |
| `release_tag` | `v1.0.0` | `github.ref_name` | Exact published semantic version tag |
| `asset_name` | `Plugin.dll` | Empty | Exact asset filename; required for multiple DLLs |

Add this job after release publication. Use your publishing job name in `needs`.
No checkout is required.

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
        kind: plugin
        asset_name: Plugin.dll
        registry_token: ${{ secrets.REGISTRY_ISSUE_TOKEN }}
```
