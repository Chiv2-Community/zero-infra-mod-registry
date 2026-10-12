# Zero Infra Mod Registry

A lightweight, infrastructure-free mod registry system for managing mod repositories, dependencies, and releases. This project provides a simple CLI to maintain a registry of mods, track their releases, and validate dependencies between different mods.

## Features

- Manage mod repositories with their metadata
- Track mod releases and version information
- Handle dependencies between mods
- Validate the package database to ensure all dependencies are satisfied
- Support for redirects to handle repository name changes
- Register native DLL releases separately from pak mods, with download source, SHA-256 and size

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

## Metadata Schemas

Use the JSON schemas to check your release metadata:

- [mod.json schema](schemas/mod.schema.json) for pak mods.
- [plugin.json schema](schemas/plugin.schema.json) for DLL plugins.

The schemas document required fields, optional media, mod and plugin dependencies, version requirements and legacy compatibility. You can reference a schema using the metadata file's `$schema` property or your editor's JSON schema settings.

Place `mod.json` for mods or `plugin.json` for plugins at the repository root before tagging a release. If you forget to create or update it for a particular release, upload the corrected file to that release's assets. The uploaded file overrides the tagged copy.

Schema validation checks the file's structure. The registry also checks version requirements and matching releases in the corresponding database, so register dependencies first.

### Validate Metadata in GitHub Actions

Add a workflow to your mod or plugin repository to validate release metadata and dependencies:

```yaml
name: Validate metadata
on: [push, pull_request]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: Chiv2-Community/zero-infra-mod-registry/actions/validate-metadata@prepare-v1
```

The action checks `mod.json` and `plugin.json` at the repository root when present, and fails if neither file exists. It validates their schemas and checks dependency versions against the published C2ModRegistry databases without downloading release assets.

Use `mod_file` and `plugin_file` for metadata stored elsewhere. Set `registry_repository` and `registry_ref` to validate against another registry or revision. For a private registry, provide `registry_token` with read access to that repository. Pin the action to a commit SHA for reproducible workflows.

## DLL Registry

You can use the registry to manage native DLL plugins separately from pak mods. To register a DLL release:

1. Add `plugin.json` to the repository root using the [plugin metadata schema](schemas/plugin.schema.json), then tag the release.
2. Register a GitHub release containing one DLL asset:
   ```sh
   uv run zero-infra-mod-registry add-dll-release https://github.com/MyOrg/MyPlugin v1.0.0
   ```
   If the release contains multiple DLLs, select one with `--dll-file MyPlugin.dll` (or the action's `dll_file` input). The filename must match exactly, including case. Missing, non-DLL, or ambiguous matches prevent registration; the registry does not select another file.
3. Validate the database and downloaded DLL content:
   ```sh
   uv run zero-infra-mod-registry validate --verify-dll-downloads
   ```
   The registry checks each DLL's size and SHA-256 against its recorded values. Each plugin version can be registered only once and cannot be overwritten by the command.

### Database Files

Plugin files are stored in `dll_db/packages/<organization>/<repository>.json` and listed in `dll_db/plugin_list_index.txt`. They use a mod-style package layout with release metadata and GitHub release notes, but no pak manifest. DLL downloads do not use the pak scanner.

Previously approved entries in `dll_db/index.json` remain readable and unchanged. When you register another version, those releases are also included in the plugin file. Conflicting legacy and per-plugin records fail validation.

The `validate` command checks both databases. Use `--dll-db-path` (or `DLL_DB_PATH`) to change the DLL database location, and `--dry-run` to validate an addition without writing it.

Registry operators should review each DLL version before publishing it. Hashes verify integrity; they do not sandbox native code or establish that a DLL is harmless.
