from __future__ import annotations

import argparse
import logging
import os

from github import Auth, Github

from zero_infra_mod_registry.registry import FilesystemPackageRegistry, PackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.models import Repo

# Configure logging
level = os.environ.get("LOG_LEVEL", "WARNING")
logging.basicConfig(
    format="%(asctime)s %(levelname)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    level=level,
)

# Default paths that can be overridden by environment variables
DEFAULT_REGISTRY_PATH = os.environ.get("REGISTRY_PATH", "./registry")
DEFAULT_PACKAGE_DB_DIR = os.environ.get("PACKAGE_DB_PATH", "./package_db")


def main() -> None:
    """Main entry point for the CLI."""
    argparser = argparse.ArgumentParser(description="Manage the mod registry.")

    # Add dry-run flag
    argparser.add_argument(
        "--dry-run", action="store_true", help="Don't actually make any changes."
    )

    # Add path configuration options
    argparser.add_argument(
        "--registry-path",
        type=str,
        default=DEFAULT_REGISTRY_PATH,
        help=f"Path to the registry directory. Default: {DEFAULT_REGISTRY_PATH}",
    )
    argparser.add_argument(
        "--package-db-path",
        type=str,
        default=DEFAULT_PACKAGE_DB_DIR,
        help=f"Path to the package database directory. Default: {DEFAULT_PACKAGE_DB_DIR}",
    )

    # Add GitHub token option
    argparser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="GitHub token to use for authentication. Defaults to GITHUB_TOKEN environment variable."
    )

    subparsers = argparser.add_subparsers(dest="command", required=True)

    init_subparser = subparsers.add_parser("init", help="Add to package list and initialize a mod repo.")
    init_subparser.add_argument(
        "repo_url", type=str, help="The repo url to add or remove."
    )

    process_registry_updates_subparser = subparsers.add_parser(
        "process-registry-updates",
        help="Find any new package list entries and load all of their releases.",
    )

    add_subparser = subparsers.add_parser("add", help="Add a release to a mod repo.")
    add_subparser.add_argument(
        "repo_url", type=str, help="The repo url to add or remove."
    )
    add_subparser.add_argument(
        "release_tag", type=str, help="The release tag to add or remove."
    )

    remove_subparser = subparsers.add_parser("remove", help="Remove mod from the repo.")
    remove_subparser.add_argument(
        "repo_url", type=str, help="The repo url to add or remove."
    )
    args = argparser.parse_args()

    # Create GitHub client and mod retriever
    auth = Auth.Token(args.github_token or os.environ.get("GITHUB_TOKEN") or "")
    github_client = Github(auth=auth)
    mod_retriever = GithubModMetadataRetriever(github_client)

    # Initialize the registry with the mod retriever
    registry: PackageRegistry = FilesystemPackageRegistry(
        mod_retriever=mod_retriever,
        registry_path=args.registry_path,
        package_db_path=args.package_db_path,
    )

    if args.command == "process-registry-updates":
        registry.process_registry_updates(args.dry_run)
    elif args.command == "init":
        [org, repoName] = args.repo_url.strip().split("/")[-2:]
        # Add the package to the index first
        registry.add_package_to_index(args.repo_url, args.dry_run)
        # Then initialize the repository
        registry.init([Repo(org, repoName)], args.dry_run)
    elif args.command == "add":
        [org, repoName] = args.repo_url.strip().split("/")[-2:]
        registry.add_release(
            Repo(org, repoName),
            args.release_tag.strip(),
            args.dry_run,
        )
    elif args.command == "remove":
        [org, repoName] = args.repo_url.strip().split("/")[-2:]
        registry.remove_mods([Repo(org, repoName)], args.dry_run)
    else:
        logging.error("Unknown command.")
        exit(1)


if __name__ == "__main__":
    main()