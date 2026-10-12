import logging
import os
import shutil
import subprocess
import tempfile
import traceback
import hashlib
from urllib.parse import urlparse
from os import environ
from typing import List, Optional, Tuple, cast, override

import requests
from github import Auth, Github, GitReleaseAsset
from github.GitRelease import GitRelease
from semver import Version

from zero_infra_mod_registry.models import Dependency, ModInfo, Mod, Release, Repo
from zero_infra_mod_registry.models.pak_manifest import Manifest, PakInventory
from zero_infra_mod_registry.models.dll_metadata import DllRelease, PluginInfo
from zero_infra_mod_registry.utils.json_types import decode_json, json_array, json_object
from zero_infra_mod_registry.retriever.mod_metadata_retriever import ModMetadataRetriever


class GithubModMetadataRetriever(ModMetadataRetriever):
    """
    Implementation of ModMetadataRetriever that retrieves metadata from GitHub repositories.
    """

    def __init__(self, github_client: Optional[Github] = None) -> None:
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

    @override
    def measure_dll(self, url: str) -> Tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            if urlparse(response.url).scheme != "https":
                raise ValueError("Insecure DLL download redirect")
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @override
    def fetch_dll_release(self, repo: Repo, release_tag: str, dll_file: str | None = None) -> DllRelease:
        release = self.github_client.get_repo(str(repo)).get_release(release_tag)
        if release.draft:
            raise ValueError("Draft DLL releases cannot be registered")
        version = str(Version.parse(release.tag_name.removeprefix("v")))
        assets = [asset for asset in release.get_assets() if asset.name.lower().endswith(".dll")]
        if dll_file is not None:
            assets = [asset for asset in assets if asset.name == dll_file]
            if len(assets) != 1:
                raise ValueError(f"Requested DLL asset must match exactly one DLL: {dll_file!r}")
        if not assets:
            raise ValueError("The release contains no DLL assets")
        if len(assets) != 1:
            raise ValueError("A DLL release must contain exactly one DLL asset unless --dll-file selects one")
        url = assets[0].browser_download_url
        DllRelease(repo.org, repo.name, version, url, "0" * 64, 1).validate()
        info = self.fetch_plugin_info(repo, release.tag_name)
        digest, size = self.measure_dll(url)
        entry = DllRelease(repo.org, repo.name, version, url, digest, size, info,
                           release.tag_name, release.published_at, release.body, assets[0].name)
        entry.validate()
        if entry.size != assets[0].size:
            raise ValueError("Downloaded DLL size differs from release asset")
        return entry

    def fetch_plugin_info(self, repo: Repo, release_tag: str) -> PluginInfo:
        url = f"https://raw.githubusercontent.com/{repo}/{release_tag}/plugin.json"
        response = requests.get(url, timeout=60)
        if response.status_code == 404:
            raise ValueError("plugin.json does not exist at the release tag; commit it before tagging the release")
        response.raise_for_status()
        if urlparse(response.url).scheme != "https":
            raise ValueError("Insecure plugin.json redirect")
        info = PluginInfo.from_dict(decode_json(response.text))
        if info.repo_url is not None and info.repo_url.lower() != repo.github_url().lower():
            raise ValueError("plugin.json repository mismatch")
        return PluginInfo(info.name, info.description, info.authors, info.plugin_dependencies,
                          info.icon_url, info.image_urls, info.mod_dependencies, repo.github_url(), info.target)

    @override
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

    @override
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

    @override
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
                traceback.print_exc()

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
        response_json = json_object(decode_json(response.text))

        response_json["repo_url"] = repo.github_url()
        mod_info = ModInfo.from_dict(response_json)
        pak = self.find_pak_file(release)

        pak_error = pak if isinstance(pak, str) else None
        dependency_errors = self.validate_dependency_versions(mod_info.mod_dependencies + mod_info.plugin_dependencies)
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

            scanner_path = os.environ.get("UNCHAINED_SCANNER_PATH")
            if not scanner_path:
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
                stdout = cast(str | bytes | None, e.stdout)
                stderr = cast(str | bytes | None, e.stderr)
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors="replace")
                logging.error(f"Stdout: {stdout}")
                logging.error(f"Stderr: {stderr}")
                raise Exception(f"UnchainedScanner failed: {stderr}")


            scanner_output_path = os.path.join(temp_dir, "manifest.json")
            with open(scanner_output_path, "r") as f:
                content = f.read()
                logging.debug(f"Pak Inventory: " + content)
                scanner_data = json_object(decode_json(content))

            paks = json_array(scanner_data.get("paks", []))
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
        paks = [asset for asset in release.get_assets() if asset.name.endswith(".pak")]

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
