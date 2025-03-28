from __future__ import annotations

import os
import warnings
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Protocol

from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry

# Display a deprecation warning
warnings.warn(
    "The package_list module is deprecated. "
    "Use the corresponding methods in FilesystemPackageRegistry instead.",
    DeprecationWarning, 
    stacklevel=2
)

# Keep the classes for backward compatibility
class PackageList(ABC):
    """Interface for package list operations."""

    @abstractmethod
    def load(self, path: str) -> List[str]:
        """Load a package list from the specified path."""
        pass

    @abstractmethod
    def generate(self, directory: str) -> List[str]:
        """Generate a package list from the specified directory."""
        pass


class TextPackageList(PackageList):
    """Implementation of PackageList that uses text files."""

    def load(self, path: str) -> List[str]:
        """Loads the package list from a file."""
        try:
            with open(path, "r") as file:
                return file.read().splitlines()
        except FileNotFoundError:
            return []

    def generate(self, directory: str) -> List[str]:
        """Gets all lines from all files, ignoring any empty lines or lines starting with #"""
        return list(
            map(repo_to_index_entry, self._get_all_text_lines_in_directory(directory))
        )

    def _get_all_text_lines_in_directory(self, directory: str) -> List[str]:
        """Gets all lines from all files, ignoring any empty lines or lines starting with #"""
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
