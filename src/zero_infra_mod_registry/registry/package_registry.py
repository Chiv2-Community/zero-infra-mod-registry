from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from zero_infra_mod_registry.models import Mod, Repo


class PackageRegistry(ABC):
    """
    An abstract interface for package registry operations.
    Defines the contract for any package registry implementation.
    """

    @abstractmethod
    def process_registry_updates(self, dry_run: bool = False) -> None:
        """
        Process updates to the registry.

        Args:
            dry_run: If True, don't make any actual changes
        """
        pass

    # Alias methods for backward compatibility
    @abstractmethod
    def init(self, repos: List[Repo], dry_run: bool = False) -> None:
        """
        Alias for add_package
        """
        pass

    @abstractmethod
    def add_release(self, repo: Repo, release_tag: str, dry_run: bool = False) -> None:
        """
        Alias for add_package_release
        """
        pass
    
    @abstractmethod
    def add_package(self, repos: List[Repo], dry_run: bool = False) -> None:
        """
        Initialize repositories by fetching their metadata and storing it.

        Args:
            repos: List of repositories to initialize
            dry_run: If True, don't make any actual changes
        """
        pass

    @abstractmethod
    def add_package_release(self, repo: Repo, release_tag: str, dry_run: bool = False) -> None:
        """
        Add a release to a repository.

        Args:
            repo: Repository to add the release to
            release_tag: Tag of the release to add
            dry_run: If True, don't make any actual changes
        """
        pass

    @abstractmethod
    def remove_mods(self, repo_list: List[Repo], dry_run: bool = False) -> None:
        """
        Remove mods from the registry.

        Args:
            repo_list: List of repositories to remove
            dry_run: If True, don't make any actual changes
        """
        pass

    @abstractmethod
    def load_mod(self, repo: Repo) -> Optional[Mod]:
        """
        Load a mod from the registry.

        Args:
            repo: Repository to load the mod for

        Returns:
            The loaded Mod object, or None if it doesn't exist
        """
        pass

    @abstractmethod
    def validate_package_db(
        self,
        additional_mods: List[Mod],
        mod_path_filter: Callable[[str], bool] = lambda x: True,
    ) -> None:
        """
        Validate the package database.

        Args:
            additional_mods: Additional mods to include in the validation
            mod_path_filter: Function to filter mod paths
        """
        pass
