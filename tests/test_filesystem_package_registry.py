import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zero_infra_mod_registry.registry.filesystem_package_registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from zero_infra_mod_registry.retriever.mod_metadata_retriever import ModMetadataRetriever
from zero_infra_mod_registry.models import Repo, Mod, Release


class TestFilesystemPackageRegistry(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = os.path.join(self.test_dir, "registry")
        self.package_db_dir = os.path.join(self.test_dir, "package_db")
        
        # Create test directories
        os.makedirs(self.registry_dir, exist_ok=True)
        os.makedirs(os.path.join(self.registry_dir, "redirects"), exist_ok=True)
        os.makedirs(self.package_db_dir, exist_ok=True)
        
        # Create a mock mod retriever
        self.mock_retriever = MagicMock(spec=ModMetadataRetriever)
        
        # Create the registry instance
        self.registry = FilesystemPackageRegistry(
            mod_retriever=self.mock_retriever,
            registry_path=self.registry_dir,
            package_db_path=self.package_db_dir,
        )
        
        # Create test files
        with open(os.path.join(self.registry_dir, "org1.txt"), "w") as f:
            f.write("https://github.com/org1/repo1\n")
            f.write("# This is a comment\n")
            f.write("https://github.com/org1/repo2\n")
            f.write("\n")  # Empty line

    def tearDown(self):
        # Remove the temporary directory and its contents
        shutil.rmtree(self.test_dir)

    def test_load_package_list(self):
        """Test loading a package list from a file."""
        # Create a test package list file
        package_list_path = os.path.join(self.test_dir, "mod_list_index.txt")
        with open(package_list_path, "w") as f:
            f.write("org1/repo1\norg2/repo2\norg3/repo3")
            
        packages = self.registry._load_package_list(package_list_path)
        self.assertEqual(len(packages), 3)
        self.assertEqual(packages, ["org1/repo1", "org2/repo2", "org3/repo3"])

    def test_get_all_text_lines_in_directory(self):
        """Test getting all text lines from files in a directory."""
        lines = self.registry._get_all_text_lines_in_directory(self.registry_dir)

        # We should have 2 non-empty, non-comment lines in total
        self.assertEqual(len(lines), 2)
        self.assertIn("https://github.com/org1/repo1", lines)
        self.assertIn("https://github.com/org1/repo2", lines)

        # Ensure comments and empty lines are ignored
        self.assertNotIn("# This is a comment", lines)
        self.assertNotIn("", lines)

    def test_generate_package_list(self):
        """Test generating a package list from a directory."""
        packages = self.registry._generate_package_list(self.registry_dir)
        self.assertEqual(len(packages), 2)
        self.assertIn("org1/repo1", packages)
        self.assertIn("org1/repo2", packages)
        
    def test_process_registry_updates_with_dry_run(self):
        """Test process_registry_updates with dry_run=True."""
        # Prepare mock and setup
        with patch.object(self.registry, 'init') as mock_init, \
             patch.object(self.registry, 'remove_mods') as mock_remove_mods:
            
            # Create an existing mod_list_index.txt with different content
            with open(self.registry.mod_list_index_path, "w") as f:
                f.write("org1/old_repo\n")
            
            # Run with dry_run=True
            self.registry.process_registry_updates(dry_run=True)
            
            # Verify the correct methods were called with dry_run=True
            mock_init.assert_called_with(unittest.mock.ANY, True)
            mock_remove_mods.assert_called_with(unittest.mock.ANY, True)
            
            # Verify mod_list_index.txt was not updated
            with open(self.registry.mod_list_index_path, "r") as f:
                content = f.read().strip()
                self.assertEqual(content, "org1/old_repo")

    def test_validate_package_db_empty(self):
        """Test validate_package_db with empty additional_mods."""
        # Just testing that it runs without exceptions
        self.registry.validate_package_db([])
                
    @patch('builtins.open')
    def test_load_mod(self, mock_open):
        """Test load_mod method."""
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = '{"name": "test-mod", "releases": []}'
        
        with patch('json.loads') as mock_loads, \
             patch('zero_infra_mod_registry.models.Mod.from_dict') as mock_from_dict:
            
            mock_loads.return_value = {"name": "test-mod", "releases": []}
            mock_mod = MagicMock()
            mock_from_dict.return_value = mock_mod
            
            repo = Repo("org1", "repo1")
            result = self.registry.load_mod(repo)
            
            self.assertEqual(result, mock_mod)
            mock_loads.assert_called_once()
            mock_from_dict.assert_called_once()

    def test_load_mod_file_not_found(self):
        """Test load_mod when file is not found."""
        repo = Repo("non_existent", "repo")
        result = self.registry.load_mod(repo)
        self.assertIsNone(result)
        
    def test_repo_to_index_entry(self):
        """Test the repo_to_index_entry function."""
        self.assertEqual(repo_to_index_entry("https://github.com/org1/repo1"), "org1/repo1")
        self.assertEqual(repo_to_index_entry("org1/repo1"), "org1/repo1")
        self.assertEqual(repo_to_index_entry("https://github.com/org1/repo1/"), "org1/repo1")
        self.assertEqual(repo_to_index_entry(" https://github.com/org1/repo1 "), "org1/repo1")


if __name__ == "__main__":
    unittest.main()
