import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from zero_infra_mod_registry.registry.filesystem_package_registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever.mod_metadata_retriever import ModMetadataRetriever


class TestPackageListFunctions(unittest.TestCase):
    """
    Tests for the package list functionality now integrated into FilesystemPackageRegistry.
    """
    
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
        # Create mock retriever
        self.mock_retriever = MagicMock(spec=ModMetadataRetriever)
        
        # Create the registry instance
        self.registry = FilesystemPackageRegistry(
            registry_path=os.path.join(self.test_dir, "registry"),
            package_db_path=os.path.join(self.test_dir, "package_db"),
            mod_retriever=self.mock_retriever
        )

        # Create a test package list file
        self.package_list_path = os.path.join(self.test_dir, "mod_list_index.txt")
        with open(self.package_list_path, "w") as f:
            f.write("org1/repo1\norg2/repo2\norg3/repo3")

        # Create a test registry directory with repository files
        self.registry_dir = os.path.join(self.test_dir, "registry")
        os.makedirs(self.registry_dir)

        # Create test repository files
        with open(os.path.join(self.registry_dir, "org1.txt"), "w") as f:
            f.write("https://github.com/org1/repo1\n")
            f.write("# This is a comment\n")
            f.write("https://github.com/org1/repo2\n")
            f.write("\n")  # Empty line

        with open(os.path.join(self.registry_dir, "org2.txt"), "w") as f:
            f.write("https://github.com/org2/repo1\n")
            f.write("https://github.com/org2/repo2\n")

    def tearDown(self):
        # Remove the temporary directory and its contents
        shutil.rmtree(self.test_dir)

    def test_repo_to_index_entry(self):
        """Test converting repository URLs to index entries."""
        self.assertEqual(
            repo_to_index_entry("https://github.com/org1/repo1"), "org1/repo1"
        )
        self.assertEqual(repo_to_index_entry("org1/repo1"), "org1/repo1")
        self.assertEqual(
            repo_to_index_entry("https://github.com/org1/repo1/"), "org1/repo1"
        )
        self.assertEqual(
            repo_to_index_entry(" https://github.com/org1/repo1 "), "org1/repo1"
        )

    def test_load_package_list(self):
        """Test loading a package list from a file."""
        packages = self.registry._load_package_list(self.package_list_path)
        self.assertEqual(len(packages), 3)
        self.assertEqual(packages, ["org1/repo1", "org2/repo2", "org3/repo3"])

    def test_load_package_list_nonexistent_file(self):
        """Test loading a package list from a nonexistent file."""
        nonexistent_path = os.path.join(self.test_dir, "nonexistent.txt")
        packages = self.registry._load_package_list(nonexistent_path)
        self.assertEqual(len(packages), 0)

    def test_get_all_text_lines_in_directory(self):
        """Test getting all text lines from files in a directory."""
        lines = self.registry._get_all_text_lines_in_directory(self.registry_dir)

        # We should have 4 non-empty, non-comment lines in total
        self.assertEqual(len(lines), 4)
        self.assertIn("https://github.com/org1/repo1", lines)
        self.assertIn("https://github.com/org1/repo2", lines)
        self.assertIn("https://github.com/org2/repo1", lines)
        self.assertIn("https://github.com/org2/repo2", lines)

        # Ensure comments and empty lines are ignored
        self.assertNotIn("# This is a comment", lines)
        self.assertNotIn("", lines)

    def test_generate_package_list(self):
        """Test generating a package list from a directory."""
        packages = self.registry._generate_package_list(self.registry_dir)
        self.assertEqual(len(packages), 4)
        self.assertIn("org1/repo1", packages)
        self.assertIn("org1/repo2", packages)
        self.assertIn("org2/repo1", packages)
        self.assertIn("org2/repo2", packages)


if __name__ == "__main__":
    unittest.main()
