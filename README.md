# Zero Infra Mod Registry

A lightweight, infrastructure-free mod registry system for managing mod repositories, dependencies, and releases. This project provides a simple CLI to maintain a registry of mods, track their releases, and validate dependencies between different mods.

## Features

- Manage mod repositories with their metadata
- Track mod releases and version information
- Handle dependencies between mods
- Validate the package database to ensure all dependencies are satisfied
- Support for redirects to handle repository name changes

## Installation

This project uses Poetry for dependency management. To set up the project:

1. Make sure you have Python 3.10 or newer installed
2. Install Poetry if you don't have it already:
   ```
   curl -sSL https://install.python-poetry.org | python3 -
   ```
3. Clone the repository:
   ```
   git clone https://github.com/yourusername/zero-infra-mod-registry.git
   cd zero-infra-mod-registry
   ```
4. Install dependencies:
   ```
   poetry install
   ```

## Using as a GitHub Action

You can use this project as a GitHub Action in your workflows. The action is implemented as a Docker container, so you don't need to install any dependencies to use it.

```yaml
jobs:
  mod-registry:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3
        
      # Example: Initialize a mod repository
      - name: Initialize mod repository
        id: init-mod
        uses: yourusername/zero-infra-mod-registry@main
        with:
          command: init
          repo_url: https://github.com/Chiv2-Community/Chiv2Turbo
          github_token: ${{ secrets.GITHUB_TOKEN }}
          
      # Example: Process registry updates with custom paths
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
          command: add
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
| `command` | Command to execute (init, process-registry-updates, add, remove, validate) | Yes | |
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

## Included GitHub Workflows

This repository includes several GitHub Workflows to automate common tasks:

### auto-update-registry.yml
Automatically processes registry updates when changes are pushed to the registry directory.

### add-release-action.yml
Allows users to add new releases by opening issues with a standardized format. The workflow:
1. Parses the JSON from the issue body
2. Adds the release to the registry
3. Commits the changes to the repository
4. Comments on the issue with the result
5. Closes the issue if successful

### action-example.yml
An example workflow demonstrating how to use the GitHub Action with manual triggers.

## Using with Docker

You can run the mod registry using Docker:

```bash
# Build the Docker image
docker build -t zero-infra-mod-registry .

# Initialize a repository
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry init https://github.com/Username/ExampleMod

# Process registry updates with custom paths
docker run -v $(pwd):/app \
  -e GITHUB_TOKEN=your_token \
  -e REGISTRY_PATH=./custom-registry \
  -e PACKAGE_DB_PATH=./custom-package-db \
  zero-infra-mod-registry process-registry-updates

# Add a release
docker run -v $(pwd):/app -e GITHUB_TOKEN=your_token zero-infra-mod-registry add https://github.com/Username/ExampleMod v1.0.0

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
poetry run python -m zero_infra_mod_registry.main init <repo_url>
```

This command both fetches the repository metadata and adds it to the registry index in a single step.

Example with custom paths:
```
poetry run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  init https://github.com/Chiv2-Community/Chiv2Turbo
```

### Process Registry Updates

Find new package list entries and load all of their releases:

```
poetry run python -m zero_infra_mod_registry.main process-registry-updates
```

With custom paths:
```
poetry run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  process-registry-updates
```

### Add a Release

Add a specific release tag to a mod repository:

```
poetry run python -m zero_infra_mod_registry.main add <repo_url> <release_tag>
```

Example with custom paths:
```
poetry run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  add https://github.com/Chiv2-Community/Chiv2Turbo v1.0.0
```

### Remove a Mod

Remove a mod from the registry:

```
poetry run python -m zero_infra_mod_registry.main remove <repo_url>
```

Example with custom paths:
```
poetry run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  remove https://github.com/Chiv2-Community/Chiv2Turbo
```

### Validate Package Registry

Validate the package registry database to ensure all dependencies are satisfied:

```
poetry run python -m zero_infra_mod_registry.main validate
```

Example with custom paths:
```
poetry run python -m zero_infra_mod_registry.main \
  --registry-path ./custom-registry \
  --package-db-path ./custom-package-db \
  validate
```



### Dry Run Mode

All commands support a `--dry-run` flag to preview changes without actually applying them:

```
poetry run python -m zero_infra_mod_registry.main --dry-run <command> <args>
```

## Testing

This project uses pytest for testing. To run the tests:

```bash
# Run all tests
poetry run pytest

# Run tests with coverage report
poetry run pytest --cov

# Run specific test file
poetry run pytest tests/test_package_list.py

# Run specific test
poetry run pytest tests/test_redirect_manager.py::TestSimpleRedirectManager::test_resolve
```

## Project Structure

- `registry/`: Contains text files listing repositories to track
- `package_db/`: Contains the processed mod data
  - `packages/`: Stores JSON files with mod metadata
  - `mod_list_index.txt`: Index of all mods in the registry
  - `redirects.txt`: Repository URL redirects
- `src/zero_infra_mod_registry/`: Source code
  - `main.py`: CLI implementation
  - `models.py`: Data models
  - `package_list.py`: Package list and redirect management
  - Other utility modules
- `tests/`: Unit tests
  - `test_package_list.py`: Tests for TextPackageList
  - `test_redirect_manager.py`: Tests for SimpleRedirectManager
- `.github/workflows/`: GitHub Actions workflow definitions
  - `auto-update-registry.yml`: Automatically updates the registry when changes are pushed
  - `add-release-action.yml`: Processes new releases submitted via issues
  - `action-example.yml`: Example workflow using the action

## Logging

You can control the log level by setting the `LOG_LEVEL` environment variable:

```
LOG_LEVEL=DEBUG poetry run python -m zero_infra_mod_registry.main <command> <args>
```

Available log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Dependencies

- Python 3.10+
- PyGithub: GitHub API integration
- requests: HTTP client
- semantic-version: Semantic versioning support
- argparse: Command-line parsing

## License

See the [LICENSE](LICENSE) file for details.
