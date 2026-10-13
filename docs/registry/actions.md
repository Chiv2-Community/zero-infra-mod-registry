# Registry action

The root Docker action runs on Linux. Checkout the registry before calling it:

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

| Input | Default | Usage |
|---|---|---|
| `command` | Required | `add-package-release`, `add-dll-release`, `remove`, `validate` |
| `repo_url` | Empty | Required for registration and removal |
| `release_tag` | Empty | Required for registration; exact published tag |
| `dll_file` | Empty | Exact DLL asset name; required for ambiguous DLL releases |
| `github_token` | `github.token` | Read access to source repositories |
| `dry_run` | `false` | Check an operation without writing files |
| `verify_dll_downloads` | `false` | Download DLLs and check recorded hashes/sizes on `validate` |
| `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `registry_path` | `./registry` | Repository records directory |
| `package_db_path` | `./package_db` | Pak database directory |
| `dll_db_path` | `./dll_db` | Plugin database directory |

The action edits workspace files. Commit them through a reviewed PR. Outputs:
`result` (command log), `failed` (`true` or `false`). Failures also fail the step.
Read log outputs through environment variables, not inline shell interpolation.

## CLI

```sh
export GITHUB_TOKEN=...
uv run zero-infra-mod-registry add-package-release https://github.com/Owner/Mod v1.0.0
uv run zero-infra-mod-registry add-dll-release https://github.com/Owner/Plugin v1.0.0 --dll-file Plugin.dll
uv run zero-infra-mod-registry validate --verify-dll-downloads
uv run zero-infra-mod-registry remove https://github.com/Owner/Mod
```

Global options: `--registry-path`, `--package-db-path`, `--dll-db-path`,
`--dry-run`. Use `--help` for command details.

For Docker, build `docker build -t registry-tool .`, then run:

```sh
docker run --rm -e GITHUB_TOKEN -v "$PWD:/github/workspace" \
  -w /github/workspace registry-tool validate --verify-dll-downloads
```
