import logging
import traceback
from os import environ
from typing import Any, List, Optional

import requests
from github import Auth, Github, GitReleaseAsset
from github.GitRelease import GitRelease
from semver import Version

from zero_infra_mod_registry.models import Dependency, Manifest, Mod, Release, Repo
from zero_infra_mod_registry.retriever.mod_metadata_retriever import (
    VALID_MOD_TYPES,
    VALID_TAGS,
    ModMetadataRetriever,
)
from zero_infra_mod_registry.utils.hashes import sha512_sum


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

            return Mod(latest_manifest=releases[0].manifest, releases=releases)
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
        (org, repoName) = mod.latest_manifest.repo_url.split("/")[-2:]
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
        return Mod(latest_manifest=mod_releases[0].manifest, releases=mod_releases)

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
                print()
                logging.error(
                    f"Mod manifest {repo} {release.tag_name} missing required field: {e}"
                )
            except Exception as e:
                has_error = True
                print()
                logging.error(
                    f"Failed to process release {repo} {release.tag_name}: {e}"
                )

        if has_error:
            print()

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
        manifest = Manifest.from_dict(response_json)
        pak = self.find_pak_file(release)

        pak_error = pak if isinstance(pak, str) else None
        tag_error = self.validate_tags(manifest.tags)
        mod_type_error = self.validate_mod_type(manifest.mod_type)
        dependency_errors = self.validate_dependency_versions(manifest.dependencies)
        tag_name_error = self.validate_version_tag_name(release.tag_name)

        if (
            pak_error
            or tag_error
            or mod_type_error
            or dependency_errors
            or tag_name_error
        ):
            all_errors: list[str] = list(filter(
                lambda x: x is not None,
                [pak_error, tag_error, mod_type_error, tag_name_error]
                + dependency_errors
            ))
            error_string = "\n\t" + "\n\t".join(all_errors)
            raise Exception(
                f"Mod manifest {repo} {release.tag_name} failed validation: {error_string}"
            )

        # Download the pak and calculate hash of pak file
        pak_asset = pak  # Ensure we're using the asset, not a potential string error
        assert not isinstance(pak_asset, str), "Expected GitReleaseAsset but got error string"
        pak_download = requests.get(pak_asset.browser_download_url)
        pak_hash = sha512_sum(pak_download.content)

        return Release(
            tag=release.tag_name,
            hash=pak_hash,
            pak_file_name=pak_asset.name,
            release_date=pak_asset.updated_at.replace(tzinfo=None),
            manifest=manifest,
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

    def validate_tags(self, tags: List[str]) -> Optional[str]:
        """
        Validate mod tags against the list of valid tags.

        Args:
            tags: List of tags to validate

        Returns:
            Error message if invalid tags found, None if all tags are valid
        """
        invalid_tags = list(filter(lambda tag: tag not in VALID_TAGS, tags))
        if len(invalid_tags) > 0:
            return f"Invalid tags: {invalid_tags}. Valid tags are: {VALID_TAGS}"
        return None

    def validate_mod_type(self, mod_type: str) -> Optional[str]:
        """
        Validate mod type against the list of valid mod types.

        Args:
            mod_type: Mod type to validate

        Returns:
            Error message if invalid mod type, None if valid
        """
        if mod_type not in VALID_MOD_TYPES:
            return f"Invalid mod type: {mod_type}. Valid types are: {VALID_MOD_TYPES}"
        return None
