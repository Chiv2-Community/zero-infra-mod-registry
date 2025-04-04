#!/bin/bash
set -e

# Default values
REGISTRY_PATH=${REGISTRY_PATH:-./registry}
PACKAGE_DB_PATH=${PACKAGE_DB_PATH:-./package_db}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Check for dry-run flag
if [ "$DRY_RUN" = "true" ]; then
  DRY_RUN_FLAG="--dry-run"
else
  DRY_RUN_FLAG=""
fi

# Set up environment variables for both Docker and GitHub Actions
export LOG_LEVEL=$LOG_LEVEL
export REGISTRY_PATH=$REGISTRY_PATH
export PACKAGE_DB_PATH=$PACKAGE_DB_PATH

# Execute the command based on the first argument
COMMAND="$1"
REPO_URL="$2"
RELEASE_TAG="$3"

case "$COMMAND" in
  init)
    if [ -z "$REPO_URL" ]; then
      echo "Error: Repository URL is required for init command"
      exit 1
    fi
    poetry run python -m zero_infra_mod_registry.main $DRY_RUN_FLAG --registry-path "$REGISTRY_PATH" --package-db-path "$PACKAGE_DB_PATH" add_package "$REPO_URL"
    ;;
    
  process-registry-updates)
    poetry run python -m zero_infra_mod_registry.main $DRY_RUN_FLAG --registry-path "$REGISTRY_PATH" --package-db-path "$PACKAGE_DB_PATH" process-registry-updates
    ;;
    
  add)
    if [ -z "$REPO_URL" ]; then
      echo "Error: Repository URL is required for add command"
      exit 1
    fi
    if [ -z "$RELEASE_TAG" ]; then
      echo "Error: Release tag is required for add command"
      exit 1
    fi
    poetry run python -m zero_infra_mod_registry.main $DRY_RUN_FLAG --registry-path "$REGISTRY_PATH" --package-db-path "$PACKAGE_DB_PATH" add_package_release "$REPO_URL" "$RELEASE_TAG"
    ;;
    
  remove)
    if [ -z "$REPO_URL" ]; then
      echo "Error: Repository URL is required for remove command"
      exit 1
    fi
    poetry run python -m zero_infra_mod_registry.main $DRY_RUN_FLAG --registry-path "$REGISTRY_PATH" --package-db-path "$PACKAGE_DB_PATH" remove "$REPO_URL"
    ;;
    
  validate)
    poetry run python -m zero_infra_mod_registry.main $DRY_RUN_FLAG --registry-path "$REGISTRY_PATH" --package-db-path "$PACKAGE_DB_PATH" validate
    ;;
    
  *)
    echo "Error: Unknown command '$COMMAND'"
    echo "Available commands: init, process-registry-updates, add, remove, validate"
    exit 1
    ;;
esac
