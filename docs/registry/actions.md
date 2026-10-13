# Registry action

The root Docker action registers, removes, or validates entries in a checked-out
registry. It runs on Linux and edits workspace files. Commit changes through a
reviewed PR. Failures fail the step.

Outputs: `result` (command log), `failed` (`true` or `false`). Read log outputs
through environment variables, not inline shell interpolation.

| Input | Example | Default | Description |
|---|---|---|---|
| `command` | `add-dll-release` | Required | `add-package-release`, `add-dll-release`, `remove`, or `validate` |
| `repo_url` | `https://github.com/Owner/Plugin` | Empty | Required for registration and removal |
| `release_tag` | `v1.0.0` | Empty | Exact published tag; required for registration |
| `dll_file` | `Plugin.dll` | Empty | Exact DLL asset name; required for ambiguous DLL releases |
| `github_token` | `${{ secrets.GITHUB_TOKEN }}` | `github.token` | Token with read access to source repositories |
| `dry_run` | `'true'` | `false` | Check an operation without writing files |
| `verify_dll_downloads` | `'true'` | `false` | Download DLLs and check recorded hashes/sizes on `validate` |
| `log_level` | `DEBUG` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `registry_path` | `./registry` | `./registry` | Repository records directory |
| `package_db_path` | `./package_db` | `./package_db` | Pak database directory |
| `dll_db_path` | `./dll_db` | `./dll_db` | Plugin database directory |

Checkout the registry before calling the action:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: Chiv2-Community/zero-infra-mod-registry@main
    with:
      command: add-dll-release
      repo_url: https://github.com/Owner/Plugin
      release_tag: v1.0.0
      dll_file: Plugin.dll
```

## CLI

The CLI runs the same registry operations locally. Set `GITHUB_TOKEN` for API
access. Pass global options before the command; use `--help` for command details.

| Option | Example | Default | Description |
|---|---|---|---|
| `--registry-path` | `./registry` | `./registry` | Repository records directory |
| `--package-db-path` | `./package_db` | `./package_db` | Pak database directory |
| `--dll-db-path` | `./dll_db` | `./dll_db` | Plugin database directory |
| `--dry-run` | `--dry-run` | Disabled | Check an operation without writing files |

```sh
export GITHUB_TOKEN=...
uv run zero-infra-mod-registry add-package-release https://github.com/Owner/Mod v1.0.0
uv run zero-infra-mod-registry add-dll-release https://github.com/Owner/Plugin v1.0.0 --dll-file Plugin.dll
uv run zero-infra-mod-registry validate --verify-dll-downloads
uv run zero-infra-mod-registry remove https://github.com/Owner/Mod
```

For Docker, build `docker build -t registry-tool .`, then run:

```sh
docker run --rm -e GITHUB_TOKEN -v "$PWD:/github/workspace" \
  -w /github/workspace registry-tool validate --verify-dll-downloads
```
