from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from semantic_version import SimpleSpec, Version

from zero_infra_mod_registry.retriever import GithubModMetadataRetriever, ModMetadataRetriever
from zero_infra_mod_registry.models import Dependency, Mod, Release, Repo
from zero_infra_mod_registry.registry.package_registry import PackageRegistry
from zero_infra_mod_registry.utils.redirect_manager import SimpleRedirectManager
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry


class PackageManagerJsonEncoder(json.JSONEncoder):
    """A custom JSON encoder that can encode datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


class FilesystemPackageRegistry(PackageRegistry):
    """
    A class that manages the filesystem-based package registry.
    This handles operations like initializing repos, adding releases, 
    processing registry updates, and removing mods.
    """

    def __init__(
        self,
        registry_path: str = os.environ.get("REGISTRY_PATH", "./registry"),
        package_db_path: str = os.environ.get("PACKAGE_DB_PATH", "./package_db"),
        mod_retriever: Optional[ModMetadataRetriever] = None,
    ):
        """
        Initialize the FilesystemPackageRegistry.
        
        Args:
            registry_path: Path to the registry directory
            package_db_path: Path to the package database directory
            mod_retriever: ModMetadataRetriever implementation to use for fetching repo and release metadata
        """
        self.registry_path = registry_path
        self.package_db_path = package_db_path
        self.packages_dir = os.path.join(package_db_path, "packages")
        self.mod_list_index_path = os.path.join(package_db_path, "mod_list_index.txt")
        self.redirects_path = os.path.join(package_db_path, "redirects.txt")
        
        # Create package_db_path directory if it doesn't exist
        if not os.path.exists(self.package_db_path):
            os.makedirs(self.package_db_path, exist_ok=True)
            
        # Create packages directory if it doesn't exist
        if not os.path.exists(self.packages_dir):
            os.makedirs(self.packages_dir, exist_ok=True)
        
        # Setup JSON encoder
        self.json_encoder = PackageManagerJsonEncoder()
        
        # Setup mod retriever
        if mod_retriever is None:
            raise ValueError("A mod_retriever must be provided")
        self.mod_retriever = mod_retriever
        
        # Load redirect manager
        self.redirect_manager = SimpleRedirectManager.from_file(self.redirects_path)

    def _load_package_list(self, path: str) -> List[str]:
        """
        Load a package list from a file.
        
        Args:
            path: Path to the file
            
        Returns:
            List of package names
        """
        try:
            with open(path, "r") as file:
                return file.read().splitlines()
        except FileNotFoundError:
            return []

    def _get_all_text_lines_in_directory(self, directory: str) -> List[str]:
        """
        Gets all lines from all files, ignoring any empty lines or lines starting with #
        
        Args:
            directory: Directory to read files from
            
        Returns:
            List of text lines
        """
        all_lines = []

        # Make sure directory exists
        if not os.path.exists(directory):
            return all_lines

        # Get all files in the directory
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)

            # Ensure it's a file and not another directory or symbolic link
            if os.path.isfile(filepath):
                with open(filepath, "r") as file:
                    for line in file:
                        line = line.strip()
                        # Exclude lines that start with '#' or are empty
                        if not line.startswith("#") and line != "":
                            all_lines.append(line)

        return all_lines

    def _generate_package_list(self, directory: str) -> List[str]:
        """
        Generate a package list from a directory.
        
        Args:
            directory: Directory to read files from
            
        Returns:
            List of package names
        """
        return list(
            map(repo_to_index_entry, self._get_all_text_lines_in_directory(directory))
        )

    def process_registry_updates(self, dry_run: bool = False) -> None:
        """
        Process updates to the registry by finding new package list entries
        and loading all of their releases.
        
        Args:
            dry_run: If True, don't make any actual changes
        """
        # Get repo lines from the registry dir
        redirects_dir = os.path.join(self.registry_path, "redirects")
        redirect_lines = self._get_all_text_lines_in_directory(redirects_dir)
        redirect_manager = SimpleRedirectManager.parse_redirects(redirect_lines)

        # Load existing redirects
        existing_redirect_manager = SimpleRedirectManager.from_file(self.redirects_path)

        logging.info(f"Loaded {len(redirect_manager.redirects)} new redirect entries.")
        logging.info(
            f"Found {len(existing_redirect_manager.redirects)} existing redirect entries."
        )

        # Write new redirects to file (if not dry run)
        if not dry_run:
            with open(self.redirects_path, "w") as file:
                file.write("\n".join(redirect_lines))
                
            # Update the instance's redirect manager
            self.redirect_manager = redirect_manager

        logging.info("Loading package list entries...")
        updated_index_entries = self._generate_package_list(self.registry_path)

        previous_index_entries = self._load_package_list(self.mod_list_index_path)

        new_entries = list(set(updated_index_entries) - set(previous_index_entries))
        removed_entries = list(set(previous_index_entries) - set(updated_index_entries))
        failed = False

        if len(new_entries) > 0:
            logging.info(f"Adding {len(new_entries)} new packages to the package list...")
            try:
                split_entries = [entry.split("/") for entry in new_entries]
                repo_entries = [Repo(entry[0], entry[1]) for entry in split_entries]
                self.init(repo_entries, dry_run)
            except Exception as e:
                # If we fail to initialize a repo, remove it from the package list
                logging.error(f"Failed to initialize repos: {e}\n")
                failed = True

        if len(removed_entries) > 0:
            logging.info(
                f"Removing {len(removed_entries)} packages from the package list..."
            )
            try:
                split_entries = [entry.split("/") for entry in removed_entries]
                repo_entries = [Repo(entry[0], entry[1]) for entry in split_entries]
                self.remove_mods(repo_entries, dry_run)
            except Exception as e:
                # If we fail to remove a repo, add it back to the package list
                logging.error(f"Failed to remove repos: {e}\n")
                failed = True

        if failed:
            logging.error(f"Failures occurred while processing the package list.")
            logging.error("The package list has not been updated.")
            return

        if dry_run:
            logging.warning("Dry run; not writing to package list.")
            return

        # Write to mod_list_index_path
        with open(self.mod_list_index_path, "w") as file:
            file.write("\n".join(updated_index_entries))

        logging.info("Package list built.")

    def init(self, repos: List[Repo], dry_run: bool = False) -> None:
        """
        Initialize repositories by fetching their metadata and storing it.
        
        Args:
            repos: List of repositories to initialize
            dry_run: If True, don't make any actual changes
        """
        logging.info(f"Initializing {len(repos)} repos...")
        mods = [self.mod_retriever.fetch_repo_metadata(repo) for repo in repos]
        filtered_mods = [mod for mod in mods if mod is not None]

        if len(filtered_mods) != len(repos):
            logging.error("Failed to initialize some repos.")
            failed_repos = [repo for repo, mod in zip(repos, mods) if mod is None]
            logging.error(f"Failed repos: {', '.join(str(repo) for repo in failed_repos)}")
            return

        self.validate_package_db(filtered_mods)

        if dry_run:
            logging.warning("Dry run; not writing to package dir.")
            return

        for mod in filtered_mods:
            [org, repoName] = mod.latest_manifest.repo_url.split("/")[-2:]

            org_dir = os.path.join(self.packages_dir, org)
            if not os.path.exists(org_dir):
                os.makedirs(org_dir, exist_ok=True)

            mod_file_path = os.path.join(self.packages_dir, org, f"{repoName}.json")
            with open(mod_file_path, "w") as file:
                file.write(self.json_encoder.encode(mod.asdict()))

            logging.info(f"Repo {org}/{repoName} initialized.")

        logging.info("Successfully initialized all repos.")

    def add_release(self, repo: Repo, release_tag: str, dry_run: bool = False) -> None:
        """
        Add a release to a repository.
        
        Args:
            repo: Repository to add the release to
            release_tag: Tag of the release to add
            dry_run: If True, don't make any actual changes
        """
        logging.info(f"Loading mod metadata for {repo}...")
        mod = self.load_mod(repo)

        if mod is None:
            logging.info(f"Mod {repo} not initialized.")
            self.init([repo], dry_run)
            # No need to continue. Initialization will get all releases.
            return

        tags = [release.tag for release in mod.releases]

        if release_tag in tags:
            logging.warning(f"Release {release_tag} already exists in repo {repo}.")
            return

        logging.info(f"Adding release {release_tag} to repo {repo}...")
        release = self.mod_retriever.fetch_release_metadata(mod, release_tag)

        if release is None:
            logging.error(f"Failed to fetch metadata for release {release_tag} from {repo}.")
            return

        updated_mod = self.mod_retriever.update_mod_with_release(mod, release)

        self.validate_package_db([updated_mod])

        if dry_run:
            logging.warning("Dry run; not writing to mod metadata.")
            return

        [org, repoName] = repo.github_url().split("/")[-2:]
        mod_file_path = os.path.join(self.packages_dir, org, f"{repoName}.json")
        with open(mod_file_path, "w") as file:
            logging.info(f"Writing updated mod metadata for {repo}...")
            file.write(self.json_encoder.encode(updated_mod.asdict()))

        logging.info(f"Successfully added release {release_tag} to repo {repo}.")

    def remove_mods(self, repo_list: List[Repo], dry_run: bool = False) -> None:
        """
        Remove mods from the registry.
        
        Args:
            repo_list: List of repositories to remove
            dry_run: If True, don't make any actual changes
        """
        logging.info(f"Removing {len(repo_list)} mods...")

        self.validate_package_db([])

        if dry_run:
            logging.warning("Dry run; not writing to mod metadata.")
            return

        for repo in repo_list:
            # Path to mod file
            org_dir = os.path.join(self.packages_dir, repo.org)
            mod_file_path = os.path.join(org_dir, f"{repo.name}.json")
            
            if os.path.exists(mod_file_path):
                os.remove(mod_file_path)
                logging.info(f"Successfully removed mod {repo}.")
            else:
                logging.warning(f"Mod file for {repo} not found at {mod_file_path}")

            # If org directory is empty, remove it
            if os.path.exists(org_dir) and not os.listdir(org_dir):
                logging.info(f"Removing empty org {repo.org}...")
                os.rmdir(org_dir)

        logging.info(f"Successfully removed {len(repo_list)} mods.")

    def load_mod(self, repo: Repo) -> Optional[Mod]:
        """
        Load a mod from the filesystem.
        
        Args:
            repo: Repository to load the mod for
            
        Returns:
            The loaded Mod object, or None if it doesn't exist
        """
        try:
            org_dir = os.path.join(self.packages_dir, repo.org)
            mod_file_path = os.path.join(org_dir, f"{repo.name}.json")
            with open(mod_file_path, "r") as file:
                mod_dict = json.loads(file.read())
                return Mod.from_dict(mod_dict)
        except FileNotFoundError:
            return None

    def validate_package_db(
        self,
        additional_mods: List[Mod],
        mod_path_filter: Callable[[str], bool] = lambda x: True,
    ) -> None:
        """
        Validate the package database by checking for missing dependencies.
        
        Args:
            additional_mods: Additional mods to include in the validation
            mod_path_filter: Function to filter mod paths
        """
        logging.info("Validating package database...")

        packages = self._load_package_list(self.mod_list_index_path)
        mods: List[Mod] = additional_mods.copy()

        # Load all mods
        for package in packages:
            [org, name] = package.split("/")
            package_path = os.path.join(self.packages_dir, org, f"{name}.json")
            if mod_path_filter(package_path):
                try:
                    with open(package_path, "r") as file:
                        mod_dict = json.loads(file.read())
                        mod = Mod.from_dict(mod_dict)

                        if mod is None:
                            logging.error(
                                f"Failed to load mod {package} during validation."
                            )
                            return

                        mods.append(mod)

                except FileNotFoundError:
                    logging.error(f"Package {package} not found during validation.")
                    return

        # Check for missing dependencies
        missing_deps: List[Tuple[Release, Dependency]] = []
        for mod in mods:
            for release in mod.releases:
                for dep in release.manifest.dependencies:
                    found_release = self._find_dependency(mods, dep)
                    if found_release is None:
                        missing_deps.append((release, dep))

        if len(missing_deps) > 0:
            logging.error(f"{len(missing_deps)} missing dependencies:")

            for release, dep in missing_deps:
                logging.error(
                    f"{release.manifest.name} {release.tag} requires missing dependency {dep.repo_url} {dep.version}"
                )

            logging.error("Package database is invalid.")
            return

        logging.info("Package database is valid.")

    def _find_dependency(self, mods: List[Mod], dep: Dependency) -> Optional[Release]:
        """
        Find a dependency in the list of mods.
        
        Args:
            mods: List of mods to search in
            dep: Dependency to find
            
        Returns:
            The found Release object, or None if not found
        """
        for mod in mods:
            for release in mod.releases:
                release_tag = release.tag
                if release_tag.startswith("v"):
                    release_tag = release_tag[1:]

                dep_version = dep.version
                if dep_version.startswith("v"):
                    dep_version = dep_version[1:]

                resolved_manifest_url = self.redirect_manager.resolve(release.manifest.repo_url)
                resolved_dep_url = self.redirect_manager.resolve(dep.repo_url)
                if resolved_manifest_url == resolved_dep_url and Version(
                    release_tag
                ) in SimpleSpec(dep_version):
                    return release

        return None