from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from zero_infra_mod_registry.models import Mod, Release, Repo
from zero_infra_mod_registry.models.dll_metadata import DllRelease

class ModMetadataRetriever(ABC):
    """
    Interface for retrieving mod metadata from a repository.
    This is the base abstract class that all metadata retrievers should extend.
    """

    def fetch_dll_release(self, repo: Repo, release_tag: str, dll_file: str | None = None) -> DllRelease:
        """Retrieve metadata and calculated integrity information for a native DLL."""
        raise NotImplementedError("This retriever does not support DLL releases")

    def measure_dll(self, url: str) -> Tuple[str, int]:
        """Download a DLL and return its SHA-256 and byte size."""
        raise NotImplementedError("This retriever does not support DLL downloads")

    @abstractmethod
    def fetch_repo_metadata(self, repo: Repo) -> Optional[Mod]:
        """
        Fetch metadata for all releases in a repository.

        Args:
            repo: Repository to fetch metadata for

        Returns:
            Mod object with metadata, or None if the repository has no valid releases
        """
        pass

    @abstractmethod
    def fetch_release_metadata(self, mod: Mod, release_tag: str) -> Optional[Release]:
        """
        Fetch metadata for a specific release.

        Args:
            mod: Mod object with repository information
            release_tag: Tag of the release to fetch

        Returns:
            Release object with metadata, or None if the release is invalid
        """
        pass

    @abstractmethod
    def update_mod_with_release(self, mod: Mod, release: Release) -> Mod:
        """
        Create a new Mod with an additional release included and sorted correctly.

        Args:
            mod: Original mod object
            release: New release to add to the mod

        Returns:
            Updated mod object with the new release
        """
        pass
