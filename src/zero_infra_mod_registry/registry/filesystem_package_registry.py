from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import Callable, List, Optional, Tuple, override

from semver import Version

from zero_infra_mod_registry.models import Dependency, Mod, Release, Repo
from zero_infra_mod_registry.models.dll_metadata import DllRelease, Plugin, dependency_matches, validate_dll_entries
from zero_infra_mod_registry.utils.json_types import JsonValue, decode_json
from zero_infra_mod_registry.registry.package_registry import PackageRegistry
from zero_infra_mod_registry.retriever import (
    ModMetadataRetriever,
)
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from zero_infra_mod_registry.utils.redirect_manager import SimpleRedirectManager


class PackageManagerJsonEncoder:
    """Encode model-produced JSON values; dates are serialized by Release."""

    def encode(self, value: JsonValue) -> str:
        return json.dumps(value, indent=4)


class FilesystemPackageRegistry(PackageRegistry):
    """
    A class that manages the filesystem-based package registry.
    This handles operations like initializing repos, adding releases,
    processing registry updates, and removing mods.
    """

    def __init__(
        self,
        mod_retriever: ModMetadataRetriever,
        registry_path: str = os.environ.get("REGISTRY_PATH", "./registry"),
        package_db_path: str = os.environ.get("PACKAGE_DB_PATH", "./package_db"),
        dll_db_path: str = os.environ.get("DLL_DB_PATH", "./dll_db"),
    ) -> None:
        """
        Initialize the FilesystemPackageRegistry.

        Args:
            registry_path: Path to the registry directory
            package_db_path: Path to the package database directory
            mod_retriever: ModMetadataRetriever implementation to use for fetching repo and release metadata
        """
        self.registry_path = registry_path
        self.package_db_path = package_db_path
        self.dll_index_path = os.path.join(dll_db_path, "index.json")
        self.plugin_list_index_path = os.path.join(dll_db_path, "plugin_list_index.txt")
        self.plugin_packages_dir = os.path.join(dll_db_path, "packages")
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

        self.mod_retriever = mod_retriever

        # Load redirect manager
        self.redirect_manager = SimpleRedirectManager.from_file(self.redirects_path)

    def _load_dll_index(self) -> List[DllRelease]:
        entries: List[DllRelease] = []
        if os.path.exists(self.dll_index_path):
            with open(self.dll_index_path) as file:
                entries = validate_dll_entries(decode_json(file.read()))
        legacy = {entry.key: entry for entry in entries}
        merged = legacy.copy()
        seen: set[str] = set()
        for package in self._load_package_list(self.plugin_list_index_path):
            if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", package) or package.lower() in seen:
                raise ValueError("Invalid or duplicate plugin index entry")
            seen.add(package.lower())
            org, name = package.split("/")
            with open(os.path.join(self.plugin_packages_dir, org, name + ".json")) as file:
                plugin = Plugin.from_dict(org, name, decode_json(file.read()))
            package_keys: set[Tuple[str, str, str]] = set()
            for entry in plugin.releases:
                if entry.key in package_keys:
                    raise ValueError("Duplicate DLL release")
                package_keys.add(entry.key)
                old = legacy.get(entry.key)
                if old is not None and old.package_dict() != entry.package_dict():
                    raise ValueError("Plugin package conflicts with legacy DLL entry")
                if entry.info is None and old is None:
                    raise ValueError("Plugin package release is missing metadata")
                merged[entry.key] = entry
        return validate_dll_entries([entry.asdict() for entry in merged.values()])

    def validate_dll_db(self, verify_downloads: bool = False) -> bool:
        try:
            entries = self._load_dll_index()
            self._validate_plugin_mod_dependencies(entries)
            if verify_downloads:
                for entry in entries:
                    actual = self.mod_retriever.measure_dll(entry.download_url)
                    if actual != (entry.sha256, entry.size):
                        raise ValueError(f"DLL content mismatch: {entry.organization}/{entry.name}:{entry.version}")
            return True
        except Exception as error:
            logging.error(f"DLL registry validation failed: {error}")
            return False

    def add_dll_release(self, repo: Repo, release_tag: str, dry_run: bool = False, dll_file: str | None = None) -> bool:
        try:
            entries = self._load_dll_index()
            entry = self.mod_retriever.fetch_dll_release(repo, release_tag, dll_file)
            entry.validate()
            if entry.info is None:
                raise ValueError("New DLL releases require plugin.json metadata")
            if entry.key in {existing.key for existing in entries}:
                raise ValueError("Duplicate DLL release")
            validate_dll_entries([release.asdict() for release in entries + [entry]])
            self._validate_plugin_mod_dependencies(entries + [entry])
            if dry_run:
                return True
            packages = self._load_package_list(self.plugin_list_index_path)
            package = next((value for value in packages if value.lower() == str(repo).lower()), str(repo))
            org, name = package.split("/")
            releases = [entry] + [old for old in entries if old.organization.lower() == repo.org.lower() and old.name.lower() == repo.name.lower()]
            paths = {os.path.join(self.plugin_packages_dir, org, name + ".json"): json.dumps(Plugin(releases).asdict(), indent=2) + "\n",
                     self.plugin_list_index_path: "\n".join(packages if package in packages else packages + [package]) + "\n"}
            self._write_plugin_files(paths)
            return True
        except Exception as error:
            logging.error(f"Failed to register DLL release: {error}")
            return False

    @staticmethod
    def _write_text_atomic(path: str, text: str) -> None:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=directory, prefix=".plugin-metadata-")
        try:
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, "w") as file:
                file.write(text)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _write_plugin_files(self, files: dict[str, str]) -> None:
        originals: dict[str, str | None] = {}
        for path in files:
            if os.path.exists(path):
                with open(path) as file:
                    originals[path] = file.read()
            else:
                originals[path] = None
        try:
            for path, text in files.items():
                self._write_text_atomic(path, text)
        except Exception:
            for path, original in originals.items():
                if original is not None:
                    self._write_text_atomic(path, original)
                elif os.path.exists(path):
                    os.unlink(path)
            raise

    def _validate_plugin_mod_dependencies(self, entries: List[DllRelease]) -> None:
        dependencies = [dependency for entry in entries if entry.info is not None for dependency in entry.info.mod_dependencies]
        if not dependencies:
            return
        mods: List[Mod] = []
        for package in self._load_package_list(self.mod_list_index_path):
            org, name = package.split("/")
            mod = self.load_mod(Repo(org, name))
            if mod is None:
                raise ValueError(f"Missing indexed mod: {package}")
            mods.append(mod)
        for dependency in dependencies:
            if self._find_dependency(mods, dependency) is None:
                raise ValueError(f"Unregistered mod dependency: {dependency.repo_url} {dependency.version}")

    @staticmethod
    def _has_plugin_dependency(entries: List[DllRelease], dependency: Dependency) -> bool:
        try:
            return any(dependency.repo_url.lower() == f"https://github.com/{entry.organization}/{entry.name}".lower()
                       and dependency_matches(entry.version, dependency.version) for entry in entries)
        except ValueError:
            return False

    @staticmethod
    def _append_index_entry(path: str, entry: str) -> None:
        # Existing indexes may have an unterminated final line.
        with open(path, "a+b") as file:
            if file.tell() > 0:
                file.seek(-1, os.SEEK_END)
                if file.read(1) != b"\n":
                    file.write(b"\n")
            file.write((entry + "\n").encode("utf-8"))

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
                return [line.strip() for line in file.read().splitlines() if line.strip()]
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
        all_lines: List[str] = []

        # Make sure directory exists
        if not os.path.exists(directory):
            return all_lines

        # Get all files in the directory
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)

            # Ensure it's a file and not another directory or symbolic link
            if os.path.isfile(filepath) and filepath.endswith(".txt"):
                logging.info(f"Reading file: {filepath}")
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

    @override
    def process_registry_updates(self, dry_run: bool = False) -> bool:
        """
        Process updates to the registry by finding new package list entries
        and loading all of their releases.

        Args:
            dry_run: If True, don't make any actual changes

        Returns:
            True if processing was successful, False otherwise
        """
        start_time = datetime.now()
        redirects_dir = os.path.join(self.registry_path, "redirects")
        redirect_lines = self._get_all_text_lines_in_directory(redirects_dir)
        redirect_manager = SimpleRedirectManager.parse_redirects(redirect_lines)

        existing_redirect_manager = SimpleRedirectManager.from_file(self.redirects_path)

        logging.info(f"Loaded {len(redirect_manager.redirects)} new redirect entries.")
        logging.info(
            f"Found {len(existing_redirect_manager.redirects)} existing redirect entries."
        )

        # Write new redirects to file (if not dry run)
        if not dry_run:
            logging.info("Writing new redirects to file " + self.redirects_path)
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
            logging.info(
                f"Adding {len(new_entries)} new packages to the package list..."
            )
            try:
                split_entries = [entry.split("/") for entry in new_entries]
                repo_entries = [Repo(entry[0], entry[1]) for entry in split_entries]
                if self.add_package(repo_entries, dry_run) != len(repo_entries):
                    failed = True
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
            return False

        if dry_run:
            logging.warning("Dry run; not writing to package list.")
            return True

        # Write to mod_list_index_path
        with open(self.mod_list_index_path, "w") as file:
            file.write("\n".join(updated_index_entries))

        logging.info("Package list built.")

        finish_time = datetime.now()
        seconds_elapsed = (finish_time - start_time).total_seconds()
        logging.info(f"Processed all registry updates in {seconds_elapsed} seconds.")


        return True

    @override
    def add_package(self, repos: List[Repo], dry_run: bool = False) -> int:
        """
        Initialize repositories by fetching their metadata and storing it, then add them to the registry index.

        Args:
            repos: List of repositories to initialize
            dry_run: If True, don't make any actual changes

        Returns:
            The number of repositories successfully initialized
        """
        logging.info(f"Initializing {len(repos)} repos...")
        mods = [self.mod_retriever.fetch_repo_metadata(repo) for repo in repos]
        filtered_mods = [mod for mod in mods if mod is not None]

        if len(filtered_mods) != len(repos):
            logging.error("Failed to initialize some repos.")
            failed_repos = [repo for repo, mod in zip(repos, mods) if mod is None]
            logging.error(
                f"Failed repos: {', '.join(str(repo) for repo in failed_repos)}"
            )
            return 0  # Return 0 for failure

        if not self.validate_package_db(filtered_mods):
            return 0

        new_maps = []
        new_blueprints = []
        new_markers = []
        new_assets = []
        new_replacements = []

        logging.info("=======================================================")
        logging.info("")
        logging.info("New packages summary")
        logging.info("")

        for mod in filtered_mods:
            logging.debug(f"{mod.latest_release_info.name}:")
            for release in mod.releases:
                logging.debug(f"\t{release.tag}:")

                if len(release.manifest.maps) > 0:
                    logging.debug("\t\tMaps:")
                    for map in release.manifest.maps:
                        logging.debug(f"\t\t\t{map.path}")
                        new_maps.append(map)

                if len(release.manifest.markers) > 0:
                    logging.debug("\t\tMarkers:")
                    for marker in release.manifest.markers:
                        logging.debug(f"\t\t\t{marker.path}")
                        new_markers.append(marker)

                if len(release.manifest.blueprints) > 0:
                    logging.debug("\t\tBlueprints:")
                    for blueprint in release.manifest.blueprints:
                        logging.debug(f"\t\t\t{blueprint.path}")
                        new_blueprints.append(blueprint)

                if len(release.manifest.replacements) > 0:
                    logging.debug("\t\tReplacements:")
                    for replacement in release.manifest.replacements:
                        logging.debug(f"\t\t\t{replacement.path}")
                        new_replacements.append(replacement)

                if len(release.manifest.arbitrary) > 0:
                    logging.debug("\t\tAssets:")
                    for asset in release.manifest.arbitrary:
                        logging.debug(f"\t\t\t{asset.path}")
                        new_assets.append(asset)

                logging.debug("")

            logging.debug("")

        logging.debug("-------------------------------------------------------")
        logging.debug("")
        logging.info(f"New maps: {len(new_maps)}")
        logging.info(f"New markers: {len(new_markers)}")
        logging.info(f"New blueprints: {len(new_blueprints)}")
        logging.info(f"New assets: {len(new_assets)}")
        logging.info("")
        logging.info(f"New Mods: {len(filtered_mods)}")
        logging.info(f"New Releases: {sum([len(mod.releases) for mod in filtered_mods])}")
        logging.info("")
        logging.info("=======================================================")

        if dry_run:
            logging.warning("Dry run; not writing to package dir or registry.")
            return len(filtered_mods)  # Return count of repos that would be initialized

        # Create registry directory if it doesn't exist
        if not os.path.exists(self.registry_path):
            os.makedirs(self.registry_path, exist_ok=True)
            logging.info(f"Created registry directory: {self.registry_path}")

        # Process each mod
        for mod in filtered_mods:
            # Parse and log the URL components
            url_parts = mod.latest_release_info.repo_url.split("/")
            logging.debug(f"URL Parts: {url_parts}")

            # Extract org and repo name
            org = url_parts[-2]
            repo_name = url_parts[-1]
            # Handle trailing slash in URL
            if repo_name == "":
                repo_name = url_parts[-2]
                org = url_parts[-3]

            logging.debug(
                f"Extracted org={org}, repoName={repo_name} from {mod.latest_release_info.repo_url}"
            )

            # Create org directory if it doesn't exist
            org_dir = os.path.join(self.packages_dir, org)
            if not os.path.exists(org_dir):
                os.makedirs(org_dir, exist_ok=True)

            # Write mod metadata to package db
            mod_file_path = os.path.join(self.packages_dir, org, f"{repo_name}.json")
            with open(mod_file_path, "w") as file:
                file.write(self.json_encoder.encode(mod.asdict()))

            # Add to registry index
            repo_url = mod.latest_release_info.repo_url
            index_entry = f"{org}/{repo_name}"

            # Debug URL parsing
            logging.info(f"Adding {index_entry} to registry, URL: {repo_url}")

            # Create org directory in registry if it doesn't exist
            registry_org_index = os.path.join(self.registry_path, f"{org}.txt")

            # Check if the entry already exists in any file in the registry
            found = False
            for root, _, files in os.walk(self.registry_path):
                for relative_path in files:
                    if relative_path.endswith(".txt"):
                        file_path = os.path.join(root, relative_path)
                        try:
                            with open(file_path, "r") as f:
                                content = f.read()
                                if repo_url in content or index_entry in content:
                                    found = True
                                    logging.debug(
                                        f"Package {index_entry} already exists in {file_path}"
                                    )
                                    break
                        except Exception as e:
                            logging.warning(f"Error reading file {file_path}: {e}")
                if found:
                    break

            if not found:
                # Write the repository URL to the file
                self._append_index_entry(registry_org_index, repo_url)
                self._append_index_entry(self.mod_list_index_path, index_entry)

                logging.info(
                    f"Added {index_entry} to the registry index at {registry_org_index}"
                )

            logging.info(f"Repo {org}/{repo_name} initialized.")

        logging.info("Successfully initialized all repos.")
        return len(filtered_mods)  # Return the count of successfully initialized repos

    def _is_package_in_index(self, repo: Repo) -> bool:
        """
        Check if a package exists in the mod list index.

        Args:
            repo: Repository to check

        Returns:
            True if the package exists in the index, False otherwise
        """
        try:
            index_entries = self._load_package_list(self.mod_list_index_path)
            index_entry = f"{repo.org}/{repo.name}"
            return index_entry in index_entries
        except Exception as e:
            logging.error(f"Failed to check if package {repo} is in index: {e}")
            return False

    @override
    def add_package_release(
        self, repo: Repo, release_tag: str, dry_run: bool = False
    ) -> bool:
        """
        Add a release to a repository.

        Args:
            repo: Repository to add the release to
            release_tag: Tag of the release to add
            dry_run: If True, don't make any actual changes

        Returns:
            1 if release was added successfully, 0 if skipped or failed, or the result from init if initialization was needed

        Raises:
            ValueError: If the package is not in the package list
        """
        # First check if the package exists in the package list
        if not self._is_package_in_index(repo):
            error_msg = f"Package {repo} is not in the package list. Add it first using the 'add-package' command."
            logging.error(error_msg)
            raise ValueError(error_msg)

        logging.info(f"Loading mod metadata for {repo}...")
        mod = self.load_mod(repo)

        if mod is None:
            logging.info(f"Mod {repo} not initialized.")
            # Initialize the repo and return the result
            return self.add_package([repo], dry_run) > 0
            # No need to continue. Initialization will get all releases.

        tags = [release.tag for release in mod.releases]

        if release_tag in tags:
            logging.warning(f"Release {release_tag} already exists in repo {repo}.")
            return False  # Return 0 for no action taken

        logging.info(f"Adding release {release_tag} to repo {repo}...")
        release = self.mod_retriever.fetch_release_metadata(mod, release_tag)

        if release is None:
            logging.error(
                f"Failed to fetch metadata for release {release_tag} from {repo}."
            )
            return False  # Return 0 for failed release metadata fetch

        new_maps = []
        new_blueprints = []
        new_markers = []
        new_assets = []
        new_replacements = []

        logging.info("=======================================================")
        logging.info("")
        logging.info("New release summary")
        logging.info("")

        if len(release.manifest.maps) > 0:
            logging.debug(f"Maps:")
            for map in release.manifest.maps:
                logging.debug(f"\t{map.path}")
                new_maps.append(map)

        if len(release.manifest.markers) > 0:
            logging.debug(f"Markers:")
            for marker in release.manifest.markers:
                logging.debug(f"\t{marker.path}")
                new_markers.append(marker)

        if len(release.manifest.blueprints) > 0:
            logging.debug(f"Blueprints:")
            for blueprint in release.manifest.blueprints:
                logging.debug(f"\t{blueprint.path}")
                new_blueprints.append(blueprint)

        if len(release.manifest.replacements) > 0:
            logging.debug(f"Replacements:")
            for replacement in release.manifest.replacements:
                logging.debug(f"\t{replacement.path}")
                new_replacements.append(replacement)

        if len(release.manifest.arbitrary) > 0:
            logging.debug(f"Assets:")
            for asset in release.manifest.arbitrary:
                logging.debug(f"\t{asset.path}")
                new_assets.append(asset)

        logging.debug("")
        logging.debug("-------------------------------------------------------")
        logging.debug("")
        logging.info(f"New maps: {len(new_maps)}")
        logging.info(f"New markers: {len(new_markers)}")
        logging.info(f"New blueprints: {len(new_blueprints)}")
        logging.info(f"New assets: {len(new_assets)}")
        logging.info("")
        logging.info("=======================================================")

        updated_mod = self.mod_retriever.update_mod_with_release(mod, release)

        if not self.validate_package_db([updated_mod]):
            return False

        if dry_run:
            logging.warning("Dry run; not writing to mod metadata.")
            return True  # Return 1 to indicate success in dry run mode

        [org, repoName] = repo.github_url().split("/")[-2:]
        mod_file_path = os.path.join(self.packages_dir, org, f"{repoName}.json")
        with open(mod_file_path, "w") as file:
            logging.info(f"Writing updated mod metadata for {repo}...")
            file.write(self.json_encoder.encode(updated_mod.asdict()))

        logging.info(f"Successfully added release {release_tag} to repo {repo}.")
        return True  # Return 1 for successful release addition

    @override
    def remove_mods(self, repo_list: List[Repo], dry_run: bool = False) -> bool:
        """
        Remove mods from the registry.

        Args:
            repo_list: List of repositories to remove
            dry_run: If True, don't make any actual changes

        Returns:
            The number of mods successfully removed
        """
        logging.info(f"Removing {len(repo_list)} mods...")

        self.validate_package_db([])

        if dry_run:
            logging.warning("Dry run; not writing to mod metadata.")
            # In dry run mode, return the number of repos that would be removed
            # Since we're processing them all without actual removal, we can just count existing files
            count = sum(
                1
                for repo in repo_list
                if os.path.exists(
                    os.path.join(self.packages_dir, repo.org, f"{repo.name}.json")
                )
            )
            return count > 0

        # Counter for successfully removed mods
        removed_count = 0

        for repo in repo_list:
            # Path to mod file
            org_dir = os.path.join(self.packages_dir, repo.org)
            mod_file_path = os.path.join(org_dir, f"{repo.name}.json")

            if os.path.exists(mod_file_path):
                os.remove(mod_file_path)
                logging.info(f"Successfully removed mod {repo}.")
                removed_count += 1
            else:
                logging.warning(f"Mod file for {repo} not found at {mod_file_path}")

            # If org directory is empty, remove it
            if os.path.exists(org_dir) and not os.listdir(org_dir):
                logging.info(f"Removing empty org {repo.org}...")
                os.rmdir(org_dir)

        logging.info(f"Successfully removed {removed_count} mods.")
        return removed_count > 0

    @override
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
                mod_dict = decode_json(file.read())
                return Mod.from_dict(mod_dict)
        except FileNotFoundError:
            return None

    @override
    def validate_package_db(
        self,
        additional_mods: List[Mod],
        mod_path_filter: Callable[[str], bool] = lambda x: True,
    ) -> bool:
        """
        Validate the package database by checking for missing dependencies.

        Args:
            additional_mods: Additional mods to include in the validation
            mod_path_filter: Function to filter mod paths
        """
        logging.info("Validating package database...")

        packages = self._load_package_list(self.mod_list_index_path)
        mods: List[Mod] = additional_mods.copy()
        supplied_packages = {repo_to_index_entry(mod.latest_release_info.repo_url) for mod in additional_mods}

        # Load all mods
        for package in packages:
            # Use the supplied replacement when initializing/recovering a repo
            # or validating a new release before its metadata is written.
            if package in supplied_packages:
                continue
            [org, name] = package.split("/")
            package_path = os.path.join(self.packages_dir, org, f"{name}.json")
            if mod_path_filter(package_path):
                try:
                    with open(package_path, "r") as file:
                        mod_dict = decode_json(file.read())
                        mod = Mod.from_dict(mod_dict)

                        mods.append(mod)

                except FileNotFoundError:
                    logging.error(f"Package {package} not found during validation.")
                    return False

        # Check for missing dependencies
        missing_deps: List[Tuple[Release, Dependency]] = []
        try:
            plugins = self._load_dll_index()
        except ValueError as error:
            logging.error("DLL registry is invalid: %s", error)
            return False
        for mod in mods:
            for release in mod.releases:
                for dep in release.info.mod_dependencies:
                    found_release = self._find_dependency(mods, dep)
                    if found_release is None:
                        missing_deps.append((release, dep))
                for dep in release.info.plugin_dependencies:
                    if not self._has_plugin_dependency(plugins, dep):
                        missing_deps.append((release, dep))

        if len(missing_deps) > 0:
            logging.error(f"{len(missing_deps)} missing dependencies:")

            for release, dep in missing_deps:
                logging.error(
                    f"{release.info.name} {release.tag} requires missing dependency {dep.repo_url} {dep.version}"
                )

            logging.error("Package database is invalid.")
            return False

        logging.info("Package database is valid.")
        return True

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

                resolved_manifest_url = self.redirect_manager.resolve(
                    release.info.repo_url
                )
                resolved_dep_url = self.redirect_manager.resolve(dep.repo_url)
                if resolved_manifest_url.lower() == resolved_dep_url.lower():
                    try:
                        if dependency_matches(release_tag, dep_version):
                            return release
                    except ValueError:
                        # If version parsing fails, skip this release
                        continue

        return None

    def is_package_initialized(self, org: str, repo_name: str) -> bool:
        """
        Check if a package has been initialized in the package database.

        Args:
            org: The organization name
            repo_name: The repository name

        Returns:
            True if the package is initialized, False otherwise
        """
        # Check if the package file exists in the package database
        mod_file_path = os.path.join(self.packages_dir, org, f"{repo_name}.json")
        return os.path.exists(mod_file_path)
