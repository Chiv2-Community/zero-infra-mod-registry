import logging
import os
import shutil
import subprocess
import tempfile
import traceback
import hashlib
from dataclasses import replace
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
from zero_infra_mod_registry.utils.version_requirements import parse_version_requirement
from mod_registry_core.json_types import JsonObject, decode_json, json_array, json_object
from mod_registry_core.registration import selected_dll_name, single_pak_name
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
        release_assets = list(release.get_assets())
        name = selected_dll_name((asset.name for asset in release_assets), dll_file)
        assets = [asset for asset in release_assets if asset.name == name]
        url = assets[0].browser_download_url
        DllRelease(repo.org, repo.name, version, url, "0" * 64, 1).validate()
        info = self.fetch_plugin_info(repo, release)
        digest, size = self.measure_dll(url)
        entry = DllRelease(repo.org, repo.name, version, url, digest, size, info,
                           release.tag_name, release.published_at, release.body, assets[0].name)
        entry.validate()
        if entry.size != assets[0].size:
            raise ValueError("Downloaded DLL size differs from release asset")
        return entry

    def _fetch_release_json(self, repo: Repo, release: GitRelease, filename: str) -> JsonObject:
        """Prefer an exact release asset; use the tagged file only if no asset exists."""
        if filename not in {"mod.json", "plugin.json"}:
            raise ValueError("Unsupported release metadata filename")
        assets = [asset for asset in release.get_assets() if asset.name == filename]
        if len(assets) > 1:
            raise ValueError(f"Release contains multiple {filename} assets")
        url = assets[0].browser_download_url if assets else f"https://raw.githubusercontent.com/{repo}/{release.tag_name}/{filename}"
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{filename} source must use HTTPS without credentials")
        logging.info(f"Downloading {filename} from {url}")
        with requests.get(url, timeout=60) as response:
            if response.status_code == 404 and not assets:
                raise ValueError(f"{filename} does not exist in the release assets or at the release tag")
            response.raise_for_status()
            redirected = urlparse(response.url)
            if redirected.scheme != "https" or not redirected.hostname or redirected.username or redirected.password:
                raise ValueError(f"Insecure {filename} redirect")
            return json_object(decode_json(response.text))

    def fetch_plugin_info(self, repo: Repo, release: GitRelease) -> PluginInfo:
        info = PluginInfo.from_dict(self._fetch_release_json(repo, release, "plugin.json"))
        if info.repo_url is not None and info.repo_url.lower() != repo.github_url().lower():
            raise ValueError("plugin.json repository mismatch")
        return replace(info, repo_url=repo.github_url())

    @override
    def fetch_release_metadata(self, repo: Repo, release_tag: str) -> Optional[Release]:
        """
        Fetch metadata for a specific GitHub release.

        Args:
            repo: Repository to fetch the release from
            release_tag: Tag of the release to fetch

        Returns:
            Release object with metadata, or None if the release is invalid
        """
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
        if release.draft:
            raise ValueError("Draft pak releases cannot be registered")
        response_json = self._fetch_release_json(repo, release, "mod.json")
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
        assets = list(release.get_assets())
        try:
            name = single_pak_name((asset.name for asset in assets), release.tag_name)
        except ValueError as error:
            return str(error)
        return next(asset for asset in assets if asset.name == name)

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
                parse_version_requirement(dependency.version)
            except ValueError as e:
                dependency_name = "/".join(dependency.repo_url.split("/")[-2:])
                errors.append(
                    f"Version Range '{dependency.version}' for dependency '{dependency_name}' does not conform to the semver spec: {e}"
                )

        return errors
