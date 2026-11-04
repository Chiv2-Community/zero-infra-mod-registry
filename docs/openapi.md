# GitHub-backed HTTP contract

[`openapi.yaml`](../openapi.yaml) describes public registry reads and publisher
release downloads using OpenAPI 3.1. There is no registry server. Paths are GitHub
file and release locations, not application routes.

The top-level server selects the **registry metadata repository**. Both release
download operations override it with `https://github.com`; their `owner` and
`repository` path parameters select the **publisher repository**, independently
of `registryOwner` and `registryRepository`.

## Read a registry

1. Fetch `package_db/mod_list_index.txt` or `dll_db/plugin_list_index.txt` from
   `https://raw.githubusercontent.com/{registryOwner}/{registryRepository}/{revision}`.
2. For each `owner/repository` line, fetch
   `package_db/packages/{owner}/{repository}.json` or
   `dll_db/packages/{owner}/{repository}.json` from the same revision.
3. Select a registered release. Pak metadata embeds its scanned manifest; there
   is no separate version or manifest route.
4. For paks, construct
   `{release.info.repo_url}/releases/download/{release.tag}/{release.pak_file_name}`.
   For DLLs, follow the stored `download_url`.
5. Follow GitHub redirects and verify final size and SHA-256 before using the file.
   Encode tags and filenames as path components; preserve exact spelling.

Defaults point to `Chiv2-Community/C2ModRegistry` at `refs/heads/main`. Use a full
commit SHA for a consistent snapshot across requests. Branch updates and CDN
caches do not provide an atomic multi-file read. Empty registries may lack one
or both indexes; a missing indexed package is an incomplete snapshot, not an
empty package.

Raw GitHub serves JSON files as `text/plain`. Response schemas describe the JSON
document after parsing that text. Indexes remain newline-delimited strings.
No JSON error envelope, pagination, search, dependency-resolution endpoint or
registry authentication mechanism is implied. GitHub owns HTTP errors, caching,
redirects and public-access limits.

## Schema reuse and scope

The YAML spec references root `schemas/*.schema.yaml` directly. Keep these files beside the spec
when loading it in tooling; there is no copied model set to update. Stored DLL
packages use `pluginPackage`, not resolved DLL runtime models. Legacy
`dependencies` compatibility remains defined by the schemas.

`dll_db/index.json` is an obsolete launcher fallback, not a current registry
route. `package_db/redirects.txt` is a registration-time dependency alias file,
not a launcher discovery endpoint. Publisher `mod.json` / `plugin.json`, issue
requests, workflow execution and the optional OIDC gateway are outside this
read/download contract; see [publishing](publishing.md) and
[registry setup](registry/README.md).

Implementation references (pinned to launcher `main` when this spec was added):

- [`GithubModRegistry`](https://github.com/Chiv2-Community/UnchainedLauncher/blob/5bd94fcdb33035e6eb624c71244e70c17b68a1a9/UnchainedLauncher.Core/Services/Mods/Registry/GithubModRegistry.cs): pak discovery, release URLs and HEAD size probes.
- [`DllManager`](https://github.com/Chiv2-Community/UnchainedLauncher/blob/5bd94fcdb33035e6eb624c71244e70c17b68a1a9/UnchainedLauncher.Core/Services/Dlls/DllManager.cs): plugin discovery, downloads and integrity checks.

Validate with `uv run pytest tests/test_openapi.py -q`.
