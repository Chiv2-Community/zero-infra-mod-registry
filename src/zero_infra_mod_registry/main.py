from __future__ import annotations

import argparse
import logging
import os
from urllib.parse import urlparse

from github import Auth, Github

from zero_infra_mod_registry.models import Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever

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


class RegistryArguments(argparse.Namespace):
    command: str
    dry_run: bool
    registry_path: str
    package_db_path: str
    dll_db_path: str
    github_token: str | None
    repo_url: str
    release_tag: str
    dll_file: str | None
    verify_dll_downloads: bool


def main() -> None:
    """Main entry point for the CLI."""
    argparser = argparse.ArgumentParser(description="Manage the mod registry.")

    argparser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "false").lower() == "true",
        help="Don't actually make any changes. Can also be set via DRY_RUN environment variable.",
    )

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
    argparser.add_argument(
        "--github-token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token to use for authentication. Can also be set via GITHUB_TOKEN environment variable.",
    )

    subparsers = argparser.add_subparsers(dest="command", required=True)

    argparser.add_argument("--dll-db-path", default=os.environ.get("DLL_DB_PATH", "./dll_db"))
    dll_subparser = subparsers.add_parser("add-dll-release", help="Register a native DLL release separately from pak mods.")
    dll_subparser.add_argument("repo_url")
    dll_subparser.add_argument("release_tag")
    dll_subparser.add_argument("--dll-file", default=os.environ.get("DLL_FILE") or None,
                               help="Exact DLL asset filename (required when a release has multiple DLLs).")

    add_subparser = subparsers.add_parser(
        "add-package-release", help="Register one pak release, creating the package if needed."
    )
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

    validate_subparser = subparsers.add_parser(
        "validate", help="Validate the package registry database."
    )
    validate_subparser.add_argument("--verify-dll-downloads", action="store_true",
                                   default=os.environ.get("VERIFY_DLL_DOWNLOADS", "false").lower() == "true")
    args = RegistryArguments()
    argparser.parse_args(namespace=args)

    # Create GitHub client and mod retriever
    auth = Auth.Token(args.github_token or "")
    github_client = Github(auth=auth)
    mod_retriever = GithubModMetadataRetriever(github_client)

    # Initialize the registry with the mod retriever
    registry = FilesystemPackageRegistry(
        mod_retriever=mod_retriever,
        registry_path=args.registry_path,
        package_db_path=args.package_db_path,
        dll_db_path=args.dll_db_path,
    )

    if args.command in {"add-package-release", "add-dll-release"}:
        url = urlparse(args.repo_url)
        parts = url.path.strip("/").split("/")
        if url.scheme != "https" or url.netloc != "github.com" or len(parts) != 2:
            argparser.error("repo_url must be https://github.com/Organization/Repository")
        repo = Repo(parts[0], parts[1])
        if args.command == "add-dll-release":
            result = registry.add_dll_release(repo, args.release_tag, args.dry_run, args.dll_file)
        else:
            result = registry.add_package_release(repo, args.release_tag, args.dry_run)
        if not result:
            exit(1)
    elif args.command == "remove":
        [org, repoName] = args.repo_url.strip().split("/")[-2:]
        registry.remove_mods([Repo(org, repoName)], args.dry_run)
    elif args.command == "validate":
        if not registry.validate_dll_db(args.verify_dll_downloads):
            exit(1)
        if not registry.validate_package_db([]):
            exit(1)
        logging.info("Validation complete!")
    else:
        logging.error("Unknown command.")
        exit(1)


if __name__ == "__main__":
    main()
