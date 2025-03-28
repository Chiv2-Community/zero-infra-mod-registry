from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class RedirectManager(ABC):
    """Interface for managing redirects."""

    @abstractmethod
    def resolve(self, repo: str) -> str:
        """Resolve a repository URL through the redirect chain."""
        pass


class SimpleRedirectManager(RedirectManager):
    """Implementation of RedirectManager that uses a dictionary of redirects."""

    def __init__(self, redirects: Dict[str, str]):
        """Initialize with a dictionary of redirects."""
        self.redirects = redirects

    @staticmethod
    def from_file(file_path: str) -> SimpleRedirectManager:
        """Create a SimpleRedirectManager from a file."""
        try:
            with open(file_path, "r") as file:
                redirect_lines = file.read().splitlines()
                return SimpleRedirectManager.parse_redirects(redirect_lines)
        except FileNotFoundError:
            return SimpleRedirectManager({})

    @staticmethod
    def parse_redirects(redirect_lines: List[str]) -> SimpleRedirectManager:
        """Parse redirect lines into a SimpleRedirectManager instance."""
        parsed_lines = []
        for line in redirect_lines:
            line = line.strip()
            if line and " -> " in line:
                parsed_lines.append(line.split(" -> "))

        redirects = {line[0]: line[1] for line in parsed_lines}
        return SimpleRedirectManager(redirects)

    def resolve(self, repo: str) -> str:
        """Resolve a repository URL through the redirect chain."""
        if repo in self.redirects:
            result = self.redirects[repo]
            return self.resolve(result)
        else:
            return repo
