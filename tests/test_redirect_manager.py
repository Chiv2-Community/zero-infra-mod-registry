import os
import shutil
import tempfile
import unittest
from pathlib import Path

from zero_infra_mod_registry.utils.redirect_manager import SimpleRedirectManager


class TestSimpleRedirectManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()

        # Create a test redirects file
        self.redirects_path = os.path.join(self.test_dir, "redirects.txt")
        with open(self.redirects_path, "w") as f:
            f.write(
                "https://github.com/old-org/repo1 -> https://github.com/new-org/repo1\n"
                + "https://github.com/old-org/repo2 -> https://github.com/new-org/repo2\n"
                + "https://github.com/temp-org/repo1 -> https://github.com/final-org/repo1\n"
                + "https://github.com/initial-org/repo1 -> https://github.com/temp-org/repo1\n"
                + "This is not a valid redirect\n"
                + "https://github.com/no-arrow-org/repo1\n"
            )

    def tearDown(self):
        # Remove the temporary directory and its contents
        shutil.rmtree(self.test_dir)

    def test_init(self):
        """Test initializing a SimpleRedirectManager with a dictionary."""
        redirects = {
            "https://github.com/old-org/repo1": "https://github.com/new-org/repo1",
            "https://github.com/old-org/repo2": "https://github.com/new-org/repo2",
        }
        manager = SimpleRedirectManager(redirects)

        self.assertEqual(len(manager.redirects), 2)
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo1"],
            "https://github.com/new-org/repo1",
        )
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo2"],
            "https://github.com/new-org/repo2",
        )

    def test_from_file(self):
        """Test creating a SimpleRedirectManager from a file."""
        manager = SimpleRedirectManager.from_file(self.redirects_path)

        # Should have 4 valid redirects
        self.assertEqual(len(manager.redirects), 4)
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo1"],
            "https://github.com/new-org/repo1",
        )
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo2"],
            "https://github.com/new-org/repo2",
        )
        self.assertEqual(
            manager.redirects["https://github.com/temp-org/repo1"],
            "https://github.com/final-org/repo1",
        )
        self.assertEqual(
            manager.redirects["https://github.com/initial-org/repo1"],
            "https://github.com/temp-org/repo1",
        )

        # Invalid lines should be ignored
        self.assertNotIn("This is not a valid redirect", manager.redirects)
        self.assertNotIn("https://github.com/no-arrow-org/repo1", manager.redirects)

    def test_from_file_nonexistent(self):
        """Test creating a SimpleRedirectManager from a nonexistent file."""
        nonexistent_path = os.path.join(self.test_dir, "nonexistent.txt")
        manager = SimpleRedirectManager.from_file(nonexistent_path)

        # Should have an empty redirects dictionary
        self.assertEqual(len(manager.redirects), 0)

    def test_parse_redirects(self):
        """Test parsing redirect lines."""
        redirect_lines = [
            "https://github.com/old-org/repo1 -> https://github.com/new-org/repo1",
            "https://github.com/old-org/repo2 -> https://github.com/new-org/repo2",
            "This is not a valid redirect",
            "https://github.com/no-arrow-org/repo1",
        ]

        # Test the static method
        manager = SimpleRedirectManager.parse_redirects(redirect_lines)
        self.assertEqual(len(manager.redirects), 2)
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo1"],
            "https://github.com/new-org/repo1",
        )
        self.assertEqual(
            manager.redirects["https://github.com/old-org/repo2"],
            "https://github.com/new-org/repo2",
        )

    def test_resolve(self):
        """Test resolving a repository URL through the redirect chain."""
        manager = SimpleRedirectManager.from_file(self.redirects_path)

        # Direct redirect
        resolved = manager.resolve("https://github.com/old-org/repo1")
        self.assertEqual(resolved, "https://github.com/new-org/repo1")

        # Chained redirect (initial -> temp -> final)
        resolved = manager.resolve("https://github.com/initial-org/repo1")
        self.assertEqual(resolved, "https://github.com/final-org/repo1")

        # No redirect
        resolved = manager.resolve("https://github.com/stable-org/repo1")
        self.assertEqual(resolved, "https://github.com/stable-org/repo1")


if __name__ == "__main__":
    unittest.main()
