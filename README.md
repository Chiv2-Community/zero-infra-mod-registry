# Zero Infra Mod Registry

A lightweight, infrastructure-free mod registry system for managing mod repositories, dependencies, and releases. This project provides a simple CLI to maintain a registry of mods, track their releases, and validate dependencies between different mods.

## Features

- Manage mod repositories with their metadata
- Track mod releases and version information
- Handle dependencies between mods
- Validate the package database to ensure all dependencies are satisfied
- Support for redirects to handle repository name changes
- Register native DLL releases separately from pak mods, with download source, SHA-256 and size

## DLL registry

Commit `plugin.json` at the repository root before tagging a DLL release:

```json
{
  "name": "My Plugin",
  "description": "What the plugin does",
  "authors": ["Author Name"],
  "mod_dependencies": [],
  "plugin_dependencies": []
}
```

Both `mod.json` and `plugin.json` support `mod_dependencies` for pak mods and
`plugin_dependencies` for DLL plugins. Existing mods' `dependencies` are read
as `mod_dependencies`, including previously published registry records.
Dependencies use the same `repo_url` and `version` fields in both files, for
example `{"repo_url": "https://github.com/MyOrg/OtherPlugin", "version": ">=1.0.0,<2.0.0"}`.
They must refer to releases in the corresponding registry with a matching version; register
dependencies first. Exact versions, comma-separated comparisons and caret ranges
are supported. `plugin.json` is read from the release tag, not the default branch.
Missing or malformed metadata rejects the registration, including dry runs.
Optional `icon_url` and `image_urls` fields work like those in `mod.json`; use
HTTPS URLs without embedded credentials. `image_urls` is a list of screenshots.

Use the same registry CLI to register a GitHub release with one DLL asset, or
select an exact asset filename when a release contains multiple DLLs:

```sh
uv run zero-infra-mod-registry add-dll-release https://github.com/MyOrg/MyPlugin v1.0.0
uv run zero-infra-mod-registry add-dll-release https://github.com/MyOrg/MyPlugin v1.0.0 --dll-file MyPlugin.dll
uv run zero-infra-mod-registry validate --verify-dll-downloads
```

`--dll-file` (or the action's `dll_file` input) is an exact, case-sensitive DLL
asset name, not a pattern. Missing, non-DLL, or ambiguous matches fail without
falling back to another file. Without it, exactly one DLL asset is required.
Only the chosen asset is downloaded and hashed; each plugin/version still has
one immutable registry entry.

DLL metadata is written to `dll_db/packages/<organization>/<repository>.json`,
with repositories listed in `dll_db/plugin_list_index.txt`, independently of
`package_db`. Like mods, each plugin file contains `latest_release_info` and
`releases`. Releases record the tag, release date, GitHub release notes Markdown,
DLL filename, download URL, SHA-256 (`hash`), byte size and plugin `info`; there is
no pak manifest. Organization/name come from the package path; version comes
from the release tag. The retriever streams the DLL without invoking the pak scanner.
Previously approved entries in `dll_db/index.json` remain readable and unchanged.
Registering another version includes those releases in the plugin file; conflicting
legacy and per-plugin records fail validation. All new registrations require `plugin.json`.

`validate` checks both databases; `--verify-dll-downloads` also checks downloaded
DLL content against registered metadata. `--dll-db-path` (or `DLL_DB_PATH`) changes
the DLL database location. `--dry-run` validates an addition without writing it.
Existing DLL versions cannot be registered again or overwritten by the command.
Registry operators should require review of each DLL version before publishing it.
Hashes establish integrity, not a sandbox or proof that native code is harmless.

## Installation

This project uses uv for dependency management. To set up the project:

1. Make sure you have Python 3.12 or newer installed (CI and Docker use 3.14)
2. Install uv if you don't have it already:
   ```
    curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Clone the repository:
   ```
    git clone https://github.com/Chiv2-Community/zero-infra-mod-registry.git
   cd zero-infra-mod-registry
   ```
4. Install dependencies:
   ```
    uv sync --all-groups
    ```

## Type checking

Run `uv run mypy .` and `uv run pytest .` before committing. Strict mypy checking
covers both production and test code, including explicit and inferred dynamic
types, untyped definitions/calls, generic type parameters, decorators and imports.
There are no file exclusions or per-module relaxations. CI runs the same command.

Use concrete dataclasses for registry records. JSON input passes through a
recursive JSON-value union, then runtime narrowing/validation before creating
models. Do not use broad catch-all annotations or type-checker suppressions.
Tests use typed API fixtures rather than dynamically typed mock attributes;
regression tests also enforce these type rules and prove invalid code is rejected.

## Using as a GitHub Action

You can use this project as a GitHub Action in your workflows. The action is implemented as a Docker container, so you don't need to install any dependencies to use it.

```yaml
jobs:
  mod-registry:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3
        
      # Example: Add a new package to the registry
      - name: Initialize package repository
        id: add-package
        uses: yourusername/zero-infra-mod-registry@main
        with:
          command: add-package
          repo_url: https://github.com/Chiv2-Community/Chiv2Turbo
          github_token: ${{ secrets.GITHUB_TOKEN }}
          
      # Example: Process registry updates (syncing any missing releases)
      - name: Process registry updates
        id: process-updates
        uses: yourusername/zero-infra-mod-registry@main
        with:
          command: process-registry-updates
          github_token: ${{ secrets.GITHUB_TOKEN }}
          registry_path: "./custom-registry"
          package_db_path: "./custom-package-db"
          
      # Example: Validate package registry
      - name: Validate registry
        id: validate-registry
        uses: yourusername/zero-infra-mod-registry@main
        with:
          command: validate
          github_token: ${{ secrets.GITHUB_TOKEN }}
          
      # Example: Add a release
      - name: Add a release
        id: add-release
        uses: yourusername/zero-infra-mod-registry@main
        with:
          command: add-package-release
          repo_url: https://github.com/Chiv2-Community/Chiv2Turbo
          release_tag: v1.0.0
          github_token: ${{ secrets.GITHUB_TOKEN }}
          
      # Example: Use the action outputs
      - name: Display output logs
        if: always()
        run: |
          echo "Process result: ${{ steps.process-updates.outputs.result }}"
          echo "Process status: ${{ steps.process-updates.outputs.failed == 'true' && 'Failed' || 'Success' }}"
```

### Action Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `command` | Command to execute (process-registry-updates, add-package, add-package-release, remove, validate) | Yes | |
| `repo_url` | Repository URL (required for init, add, and remove commands) | For some commands | '' |
| `release_tag` | Release tag (required for add command) | For add command | '' |
| `dry_run` | Run in dry-run mode without making changes | No | 'false' |
| `github_token` | GitHub token for API access | Yes | ${{ github.token }} |
| `log_level` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | No | 'INFO' |
| `registry_path` | Path to the registry directory | No | './registry' |
| `package_db_path` | Path to the package database directory | No | './package_db' |

### Action Outputs

| Output | Description |
|--------|-------------|
| `result` | The complete output log from the command execution |
| `failed` | Whether the command failed or not ('true' or 'false') |

These outputs can be used in subsequent steps to capture logs, make decisions based on command success/failure, or display results in comments or summaries.

## Using with Docker

You can run the mod registry using Docker:

```bash
# Build the Docker image
docker build -t zero-infra-mod-registry .

# Initialize a repository
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry add-package https://github.com/Username/ExampleMod

# Process registry updates with custom paths
docker run -v $(pwd):/app \
  -e GITHUB_TOKEN=your_token \
  -e REGISTRY_PATH=./custom-registry \
  -e PACKAGE_DB_PATH=./custom-package-db \
  zero-infra-mod-registry process-registry-updates

# Add a release
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry add-package-release https://github.com/Username/ExampleMod v1.0.0

# Remove a mod
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry remove https://github.com/Username/ExampleMod

# Validate the package registry database
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry validate

# Run in dry-run mode
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token -e DRY_RUN=true zero-infra-mod-registry process-registry-updates
```

### Docker Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub token for API access | Required |
| `DRY_RUN` | Run in dry-run mode without making changes | false |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | INFO |
| `REGISTRY_PATH` | Path to the registry directory | ./registry |
| `PACKAGE_DB_PATH` | Path to the package database directory | ./package_db |

## Manual Usage

The tool provides several CLI commands to manage the mod registry:

### Initialize a Mod Repository

Add a new mod repository to the registry and package list:

```
uv run python -m zero_infra_mod_registry.main add-package <repo_url>
```

This command both fetches the repository metadata and adds it to the registry index in a single step.

Example with custom paths:
```
uv run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  add-package https://github.com/Chiv2-Community/Chiv2Turbo
```

### Process Registry Updates

Find new package list entries and load all of their releases:

```
uv run python -m zero_infra_mod_registry.main process-registry-updates
```

With custom paths:
```
uv run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  process-registry-updates
```

### Add a Release

Add a specific release tag to a mod repository:

```
uv run python -m zero_infra_mod_registry.main add-package-release <repo_url> <release_tag>
```

Example with custom paths:
```
uv run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  add-package-release https://github.com/Chiv2-Community/Chiv2Turbo v1.0.0
```

### Remove a Mod

Remove a mod from the registry:

```
uv run python -m zero_infra_mod_registry.main remove <repo_url>
```

Example with custom paths:
```
uv run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  remove https://github.com/Chiv2-Community/Chiv2Turbo
```

### Validate Package Registry

Validate the package registry database to ensure all dependencies are satisfied:

```
uv run python -m zero_infra_mod_registry.main validate
```

Example with custom paths:
```
uv run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  validate
```



### Dry Run Mode

All commands support a `--dry-run` flag to preview changes without actually applying them:

```
uv run python -m zero_infra_mod_registry.main --dry-run <command> <args>
```

## Testing

This project uses pytest for testing. To run the tests:

```bash
uv run pytest
```

## Logging

You can control the log level by setting the `LOG_LEVEL` environment variable:

```
LOG_LEVEL=DEBUG uv run python -m zero_infra_mod_registry.main <command> <args>
```

Available log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Dependencies

- Python 3.12+
- PyGithub: GitHub API integration
- requests: HTTP client
- semver: Semantic versioning support
- argparse: Command-line parsing

## License

See the [LICENSE](LICENSE) file for details.
