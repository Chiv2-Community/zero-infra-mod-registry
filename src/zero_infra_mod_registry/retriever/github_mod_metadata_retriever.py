import logging
import os
import shutil
import subprocess
import tempfile
import traceback
import json
from os import environ, mkdir
from typing import Any, List, Optional, TypeGuard, cast

import requests
from github import Auth, Github, GitReleaseAsset
from github.GitRelease import GitRelease
from semver import Version

from zero_infra_mod_registry.models import Dependency, ModInfo, Mod, Release, Repo
from zero_infra_mod_registry.models.manifest import Manifest, PakInventory
from zero_infra_mod_registry.retriever.mod_metadata_retriever import ModMetadataRetriever


class GithubModMetadataRetriever(ModMetadataRetriever):
    """
    Implementation of ModMetadataRetriever that retrieves metadata from GitHub repositories.
    """

    def __init__(self, github_client: Optional[Github] = None):
        """
        Initialize a GithubModMetadataRetriever with an optional GitHub client.
        If no client is provided, one will be created using the GITHUB_TOKEN environment variable.

        Args:
            github_client: Optional GitHub client to use
        """
        if github_client is None:
            auth = Auth.Token(environ.get("GITHUB_TOKEN") or "")
            self.github_client = Github(auth=auth)
        else:
            self.github_client = github_client

    def fetch_repo_metadata(self, repo: Repo) -> Optional[Mod]:
        """
        Fetch metadata for all releases in a GitHub repository.

        Args:
            repo: Repository to fetch metadata for

        Returns:
            Mod object with metadata, or None if the repository has no valid releases
        """
        try:
            releases = self.fetch_all_releases(repo)

            if len(releases) == 0:
                logging.warning(f"Repo {repo} has no valid releases.")
                return None

            return Mod(latest_release_info=releases[0].info, releases=releases)
        except Exception as e:
            logging.error(f"Failed to fetch metadata for repo {repo}: {e}")
            return None

    def fetch_release_metadata(self, mod: Mod, release_tag: str) -> Optional[Release]:
        """
        Fetch metadata for a specific GitHub release.

        Args:
            mod: Mod object with repository information
            release_tag: Tag of the release to fetch

        Returns:
            Release object with metadata, or None if the release is invalid
        """
        (org, repoName) = mod.latest_release_info.repo_url.split("/")[-2:]
        repo = Repo(org, repoName)
        try:
            repoString = str(repo)

            logging.info(f"Fetching repo '{repoString}'")
            github_repo = self.github_client.get_repo(repoString)

            logging.info(
                f"Successfully Retrieved repository. Fetching release '{release_tag}'"
            )
            release = github_repo.get_release(release_tag)

            return self.process_release(repo, release)

        except Exception as e:
            logging.error(
                f"Failed to fetch metadata for release '{release_tag}' in repo '{repo}': {e}"
            )
            traceback.print_exc()
            return None

    def update_mod_with_release(self, mod: Mod, release: Release) -> Mod:
        """
        Create a new Mod with an additional release included and sorted correctly.

        Args:
            mod: Original mod object
            release: New release to add to the mod

        Returns:
            Updated mod object with the new release
        """
        mod_releases = mod.releases + [release]
        mod_releases.sort(key=lambda x: x.release_date, reverse=True)
        return Mod(latest_release_info=mod_releases[0].info, releases=mod_releases)

    def fetch_all_releases(self, repo: Repo) -> List[Release]:
        """
        Fetch metadata for all releases in a GitHub repository.

        Args:
            repo: Repository to fetch all releases for

        Returns:
            List of Release objects with metadata
        """
        logging.info(f"Getting all releases for {repo}")
        github_repo = self.github_client.get_repo(str(repo))
        git_releases = github_repo.get_releases()

        logging.info(f"Found {git_releases.totalCount} releases for {repo}")
        results = []
        has_error = False
        for release in git_releases:
            try:
                logging.info(f"Processing release {release.tag_name} for {repo}")
                results.append(self.process_release(repo, release))
            except KeyError as e:
                has_error = True
                logging.error(
                    f"Mod info {repo} {release.tag_name} missing required field: {e}"
                )
            except Exception as e:
                has_error = True
                logging.error(
                    f"Failed to process release {repo} {release.tag_name}: {e}"
                )

        results.sort(key=lambda x: x.release_date, reverse=True)

        logging.info(f"Successfully processed {len(results)} releases for {repo}")
        return results

    def process_release(self, repo: Repo, release: GitRelease) -> Release:
        """
        Process a single GitHub release and return a Release object.

        Args:
            repo: Repository the release is from
            release: GitHub release object

        Returns:
            Release object with metadata

        Raises:
            Exception: If the release fails validation
        """
        # Download the mod json
        mod_json_url = (
            f"https://raw.githubusercontent.com/{repo}/{release.tag_name}/mod.json"
        )

        logging.info(f"Downloading mod.json from {mod_json_url}")
        response = requests.get(mod_json_url)

        if response.status_code == 404:
            raise Exception(f"mod.json does not exist for this release.")
        elif response.status_code != 200:
            raise Exception(
                f"Failed to download mod.json from {mod_json_url} with status code {response.status_code}"
            )

        logging.info(f"Successfully downloaded mod.json")
        response_json = response.json()

        response_json["repo_url"] = repo.github_url()
        mod_info = ModInfo.from_dict(response_json)
        pak = self.find_pak_file(release)

        pak_error = pak if isinstance(pak, str) else None
        dependency_errors = self.validate_dependency_versions(mod_info.dependencies)
        tag_name_error = self.validate_version_tag_name(release.tag_name)

        if (
            pak_error
            or dependency_errors
            or tag_name_error
        ):
            # Collect all errors and filter out None values
            error_list: List[Optional[str]] = [pak_error, tag_name_error]
            all_errors: List[str] = [x for x in error_list if x is not None]
            all_errors.extend(dependency_errors)
            error_string = "\n\t" + "\n\t".join(all_errors)
            raise Exception(
                f"Mod manifest {repo} {release.tag_name} failed validation: {error_string}"
            )

        assert not isinstance(pak, str), "Expected GitReleaseAsset but got error string"
        pak_asset: GitReleaseAsset.GitReleaseAsset = pak

        with tempfile.TemporaryDirectory() as temp_dir:
            pak_path = os.path.join(temp_dir, pak_asset.name)
            logging.info(f"Downloading pak file from {pak_asset.browser_download_url} to {pak_path}")
            
            with requests.get(pak_asset.browser_download_url, stream=True) as r:
                r.raise_for_status()
                with open(pak_path, "wb") as f:
                    shutil.copyfileobj(r.raw, f)

            scanner_path = os.path.abspath(os.path.join(os.getcwd(), "bin", "UnchainedScanner"))
            if not os.path.exists(scanner_path):
                raise Exception(f"UnchainedScanner not found at {scanner_path}")

            logging.info(f"Running UnchainedScanner on {pak_path}")
            try:
                subprocess.run(
                    [scanner_path, "scan", "--pak", temp_dir, "--out", temp_dir],
                    check=True,
                    capture_output=True,
                    text=True
                )
                manifest_path = os.path.join(temp_dir, "manifest.json")
                if not os.path.exists(manifest_path):
                    raise Exception(f"UnchainedScanner output not found at {manifest_path}")
                logging.info(f"UnchainedScanner output found at {manifest_path}")

            except subprocess.CalledProcessError as e:
                logging.error(f"UnchainedScanner failed with exit code {e.returncode}")
                logging.error(f"Stdout: {e.stdout}")
                logging.error(f"Stderr: {e.stderr}")
                raise Exception(f"UnchainedScanner failed: {e.stderr}")


            scanner_output_path = os.path.join(temp_dir, "manifest.json")
            with open(scanner_output_path, "r") as f:
                scanner_data = json.load(f)

            paks = scanner_data.get("paks", [])
            if not paks:
                raise Exception(f"Pak scanner returned no .pak files for {pak_path}")

            pak_inventory_data = paks[0]
            pak_inventory = PakInventory.from_dict(pak_inventory_data)
            blueprint_count = len(pak_inventory.inventory.blueprints)
            replacement_count = len(pak_inventory.inventory.replacements)
            marker_count = len(pak_inventory.inventory.markers)
            map_count = len(pak_inventory.inventory.maps)
            logging.info(f"Pak inventory successfully loaded from scanner output. Found {blueprint_count} blueprints, {replacement_count} replacements, {marker_count} markers, and {map_count} maps.")

        return Release(
            tag=release.tag_name,
            hash=pak_inventory.pak_hash or "",
            pak_file_name=pak_asset.name,
            release_date=pak_asset.updated_at.replace(tzinfo=None),
            info=mod_info,
            release_notes_markdown=release.body or None,
            manifest=pak_inventory.inventory
        )

    def find_pak_file(self, release: GitRelease) -> str | GitReleaseAsset.GitReleaseAsset:
        """
        Find a .pak file in the release assets.

        Args:
            release: GitHub release object

        Returns:
            Asset object representing the .pak file, or an error string if not found or multiple found
        """
        paks = list(
            filter(lambda asset: asset.name.endswith(".pak"), release.get_assets())
        )

        if len(paks) == 0:
            return f"No pak file found for release {release.tag_name}."

        if len(paks) > 1:
            return f"Multiple pak files found for release {release.tag_name}."

        pak = paks[0]

        return pak

    def validate_version_tag_name(self, tag_name: str) -> Optional[str]:
        """
        Validate that a version tag follows semantic versioning.

        Args:
            tag_name: Version tag to validate

        Returns:
            Error message if invalid, None if valid
        """
        if tag_name.startswith("v"):
            tag_name = tag_name[1:]

        try:
            Version.parse(tag_name)
            return None
        except ValueError as e:
            return f"Version Tag '{tag_name}' Does not conform to the semver spec: {e}"

    def validate_dependency_versions(self, dependencies: List[Dependency]) -> List[str]:
        """
        Validate dependency version specifications.

        Args:
            dependencies: List of dependencies to validate

        Returns:
            List of error messages for invalid dependencies
        """
        errors = []
        for dependency in dependencies:
            try:
                input_version_range = dependency.version
                if input_version_range.startswith("v"):
                    input_version_range = input_version_range[1:]
                
                # Handle caret notation like "^1.0.0" - transform to semver format
                if input_version_range.startswith("^"):
                    input_version_range = ">=" + input_version_range[1:]
                
                # Handle comma-separated version ranges like ">=1.0.0,<2.0.0"
                # Transform to semver format by checking each range separately
                if "," in input_version_range:
                    parts = input_version_range.split(",")
                    for part in parts:
                        test_version = Version.parse("1.0.0")
                        test_version.match(part.strip())
                else:
                    test_version = Version.parse("1.0.0")
                    test_version.match(input_version_range)
            except ValueError as e:
                dependency_name = "/".join(dependency.repo_url.split("/")[-2:])
                errors.append(
                    f"Version Range '{dependency.version}' for dependency '{dependency_name}' does not conform to the semver spec: {e}"
                )

        return errors
