from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import Callable, List, Optional, Tuple, override

from semver import Version

from zero_infra_mod_registry.models import Dependency, Mod, Release, Repo
from zero_infra_mod_registry.models.dll_metadata import DllRelease, Plugin, validate_dll_entries, validate_dll_releases
from zero_infra_mod_registry.utils.version_requirements import dependency_matches
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
    This handles registering individual releases and removing mods.
    """

    def __init__(
        self,
        mod_retriever: ModMetadataRetriever | None = None,
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
        if mod_retriever is not None and not os.path.exists(self.package_db_path):
            os.makedirs(self.package_db_path, exist_ok=True)

        # Create packages directory if it doesn't exist
        if mod_retriever is not None and not os.path.exists(self.packages_dir):
            os.makedirs(self.packages_dir, exist_ok=True)

        # Setup JSON encoder
        self.json_encoder = PackageManagerJsonEncoder()

        self.mod_retriever = mod_retriever

        # Load redirect manager
        self.redirect_manager = SimpleRedirectManager.from_file(self.redirects_path)

    def _require_retriever(self) -> ModMetadataRetriever:
        if self.mod_retriever is None:
            raise ValueError("This registry has no release retriever; only local validation is available")
        return self.mod_retriever

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
        releases = list(merged.values())
        validate_dll_releases(releases)
        return releases

    def validate_dll_db(self, verify_downloads: bool = False) -> bool:
        try:
            entries = self._load_dll_index()
            self._validate_plugin_mod_dependencies(entries)
            if verify_downloads:
                for entry in entries:
                    actual = self._require_retriever().measure_dll(entry.download_url)
                    if actual != (entry.sha256, entry.size):
                        raise ValueError(f"DLL content mismatch: {entry.organization}/{entry.name}:{entry.version}")
            return True
        except Exception as error:
            logging.error(f"DLL registry validation failed: {error}")
            return False

    def add_dll_release(self, repo: Repo, release_tag: str, dry_run: bool = False, dll_file: str | None = None) -> bool:
        try:
            entries = self._load_dll_index()
            entry = self._require_retriever().fetch_dll_release(repo, release_tag, dll_file)
            entry.validate()
            if entry.info is None:
                raise ValueError("New DLL releases require plugin.json metadata")
            if entry.key in {existing.key for existing in entries}:
                raise ValueError("Duplicate DLL release")
            validate_dll_releases(entries + [entry])
            self._validate_plugin_mod_dependencies(entries + [entry])
            if dry_run:
                return True
            packages = self._load_package_list(self.plugin_list_index_path)
            package = next((value for value in packages if value.lower() == str(repo).lower()), str(repo))
            org, name = package.split("/")
            releases = [entry] + [old for old in entries if old.organization.lower() == repo.org.lower() and old.name.lower() == repo.name.lower()]
            paths = {os.path.join(self.plugin_packages_dir, org, name + ".json"): json.dumps(Plugin(releases).asdict(), indent=2) + "\n",
                     self.plugin_list_index_path: "\n".join(packages if package in packages else packages + [package]) + "\n"}
            self._write_registry_files(paths)
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

    def _write_registry_files(self, files: dict[str, str]) -> None:
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
        self.validate_metadata_dependencies(dependencies, [])

    def validate_metadata_dependencies(self, mod_dependencies: List[Dependency], plugin_dependencies: List[Dependency]) -> None:
        """Validate release metadata dependencies against this published database."""
        plugins = self._load_dll_index() if plugin_dependencies else []
        for dependency in plugin_dependencies:
            if not self._has_plugin_dependency(plugins, dependency):
                raise ValueError(f"Unregistered plugin dependency: {dependency.repo_url} {dependency.version}")
        dependencies = mod_dependencies
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

    @override
    def add_package_release(
        self, repo: Repo, release_tag: str, dry_run: bool = False
    ) -> bool:
        """Register only the requested pak release, creating its package if needed."""
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", str(repo)) or repo.name in {".", ".."}:
                raise ValueError("Invalid pak repository identity")
            version = Version.parse(release_tag.removeprefix("v"))
            packages = self._load_package_list(self.mod_list_index_path)
            package = next((value for value in packages if value.lower() == str(repo).lower()), str(repo))
            org, name = package.split("/")
            mod = self.load_mod(Repo(org, name))
            if package in packages and mod is None:
                raise ValueError(f"Missing indexed package: {package}")
            if mod is not None and any(Version.parse(old.tag.removeprefix("v")) == version for old in mod.releases):
                raise ValueError(f"Release {release_tag} already exists in repo {repo}")

            retriever = self._require_retriever()
            release = retriever.fetch_release_metadata(Repo(org, name), release_tag)
            if release is None:
                raise ValueError(f"Failed to fetch metadata for release {release_tag} from {repo}")
            if release.tag != release_tag or release.info.repo_url.lower() != repo.github_url().lower():
                raise ValueError("Retrieved pak release does not match the requested repository and tag")
            updated_mod = Mod(release.info, [release]) if mod is None else retriever.update_mod_with_release(mod, release)
            if not self.validate_package_db([updated_mod]):
                return False
            if dry_run:
                return True

            org_index_path = os.path.join(self.registry_path, org + ".txt")
            urls = self._load_package_list(org_index_path)
            url = Repo(org, name).github_url()
            if not any(repo_to_index_entry(value).lower() == package.lower() for value in urls if not value.startswith("#")):
                urls.append(url)
            paths = {
                os.path.join(self.packages_dir, org, name + ".json"): self.json_encoder.encode(updated_mod.asdict()) + "\n",
                self.mod_list_index_path: "\n".join(packages if package in packages else packages + [package]) + "\n",
                org_index_path: "\n".join(urls) + "\n",
            }
            self._write_registry_files(paths)
            logging.info(f"Successfully added release {release_tag} to repo {repo}.")
            return True
        except Exception as error:
            logging.error(f"Failed to register pak release: {error}")
            return False

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
