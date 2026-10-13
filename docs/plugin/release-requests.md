# Request release registration

After publishing a GitHub release, call `actions/request-release`. Create a
fine-grained token with **Issues: write** access to the destination registry and
store it as `REGISTRY_ISSUE_TOKEN` in the publisher repository. The publisher's
`GITHUB_TOKEN` is scoped to its own repository; use the separate token for the
registry issue.

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

Use the actual publishing job name in `needs`. No checkout is required.

| Input | Default | Usage |
|---|---|---|
| `kind` | Required | `plugin` for DLLs, `mod` for pak assets |
| `registry_token` | Required | Issues write token for the registry |
| `registry_repository` | `Chiv2-Community/C2ModRegistry` | Destination owner/repository |
| `source_token` | `github.token` | Read access to the release repository |
| `source_repository` | `github.repository` | Release owner/repository |
| `release_tag` | `github.ref_name` | Exact published semantic version tag |
| `asset_name` | Empty | Exact asset name; required if there are multiple DLLs |

The action verifies the published release and an uploaded, nonempty asset before
creating an issue. For plugins, `asset_name` is included as `dll_file` in the
request. For mods, it checks asset presence; registration scans the release's pak
assets. Output: `issue_url`.

Reruns reuse an existing open or closed issue identified by repository and tag.
Serialize requests for the same repository/tag using concurrency. Failed registry
processing is retried by correcting the request or release and replying `retry`
on that issue. Registration opens an approval PR; maintainers merge it.
