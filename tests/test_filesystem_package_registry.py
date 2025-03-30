import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zero_infra_mod_registry.registry.filesystem_package_registry import FilesystemPackageRegistry
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry
from zero_infra_mod_registry.retriever.mod_metadata_retriever import ModMetadataRetriever
from zero_infra_mod_registry.models import Repo, Mod, Release, Manifest


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


class TestAddRelease(unittest.TestCase):
    """Tests for the FilesystemPackageRegistry.add_release method."""

    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.test_dir, "registry")
        os.makedirs(self.registry_path, exist_ok=True)
        self.package_db_path = os.path.join(self.test_dir, "package_db")
        os.makedirs(os.path.join(self.package_db_path, "packages"), exist_ok=True)
        
        # Create the mod_list_index.txt file
        self.mod_list_index_path = os.path.join(self.package_db_path, "mod_list_index.txt")
        with open(self.mod_list_index_path, "w") as f:
            f.write("testorg/testrepo\n")
        
        # Create a mock mod_retriever
        self.mock_retriever = MagicMock()
        
        # Create the registry
        self.registry = FilesystemPackageRegistry(
            mod_retriever=self.mock_retriever,
            registry_path=self.registry_path,
            package_db_path=self.package_db_path
        )
        
        # Test repo
        self.test_repo = Repo("testorg", "testrepo")
        self.nonexistent_repo = Repo("nonexistent", "repo")
    
    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_add_release_fails_if_package_not_in_index(self):
        """Test that add_release fails if the package is not in the package list."""
        with self.assertRaises(ValueError) as context:
            self.registry.add_release(self.nonexistent_repo, "v1.0.0")
        
        self.assertIn("not in the package list", str(context.exception))
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_release_succeeds_if_package_in_index(self, mock_logging):
        """Test that add_release succeeds if the package is in the package list."""
        # Mock the load_mod method to return None so we trigger the init call
        self.registry.load_mod = MagicMock(return_value=None)
        self.registry.init = MagicMock()
        
        # Call add_release
        self.registry.add_release(self.test_repo, "v1.0.0")
        
        # Verify that init was called
        self.registry.init.assert_called_once_with([self.test_repo], False)
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_release_initializes_if_mod_not_found(self, mock_logging):
        """Test that add_release initializes the repo if the mod is not found."""
        # Mock the load_mod method to return None
        self.registry.load_mod = MagicMock(return_value=None)
        self.registry.init = MagicMock()
        
        # Call add_release
        self.registry.add_release(self.test_repo, "v1.0.0")
        
        # Verify that the correct methods were called
        self.registry.load_mod.assert_called_once_with(self.test_repo)
        self.registry.init.assert_called_once_with([self.test_repo], False)
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_release_fetches_release_metadata(self, mock_logging):
        """Test that add_release fetches release metadata for new releases."""
        # Create a mock mod
        mock_mod = MagicMock(spec=Mod)
        mock_mod.releases = []
        
        # Mock the load_mod method to return our mock mod
        self.registry.load_mod = MagicMock(return_value=mock_mod)
        
        # Mock the fetch_release_metadata method
        mock_release = MagicMock(spec=Release)
        self.mock_retriever.fetch_release_metadata = MagicMock(return_value=mock_release)
        
        # Mock update_mod_with_release
        updated_mod = MagicMock(spec=Mod)
        self.mock_retriever.update_mod_with_release = MagicMock(return_value=updated_mod)
        
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call add_release
        self.registry.add_release(self.test_repo, "v1.0.0", dry_run=True)
        
        # Verify that the correct methods were called
        self.mock_retriever.fetch_release_metadata.assert_called_once_with(mock_mod, "v1.0.0")
        self.mock_retriever.update_mod_with_release.assert_called_once_with(mock_mod, mock_release)
        self.registry.validate_package_db.assert_called_once_with([updated_mod])


class TestAddPackageToIndex(unittest.TestCase):
    """Tests for the FilesystemPackageRegistry.add_package_to_index method.
    
    Note: This method is used internally by the 'init' command
    and not exposed directly as a CLI command.
    """
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.test_dir, "registry")
        os.makedirs(self.registry_path, exist_ok=True)
        self.package_db_path = os.path.join(self.test_dir, "package_db")
        
        # Create a mock mod_retriever
        self.mock_retriever = MagicMock()
        
        # Create the registry
        self.registry = FilesystemPackageRegistry(
            mod_retriever=self.mock_retriever,
            registry_path=self.registry_path,
            package_db_path=self.package_db_path
        )
    
    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_package_creates_file(self, mock_logging):
        """Test that add_package_to_index creates a file with the repository URL."""
        repo_url = "https://github.com/testorg/testrepo"
        
        # Call the method
        self.registry.add_package_to_index(repo_url)
        
        # Check that the file was created
        expected_file_path = os.path.join(self.registry_path, "testorg/testrepo.txt")
        self.assertTrue(os.path.exists(expected_file_path), f"File {expected_file_path} was not created")
        
        # Check the content of the file
        with open(expected_file_path, "r") as f:
            content = f.read().strip()
            self.assertEqual(content, repo_url)
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_package_dry_run(self, mock_logging):
        """Test that add_package_to_index in dry run mode doesn't create a file."""
        repo_url = "https://github.com/testorg/testrepo"
        
        # Call the method in dry run mode
        self.registry.add_package_to_index(repo_url, dry_run=True)
        
        # Check that the file was not created
        expected_file_path = os.path.join(self.registry_path, "testorg/testrepo.txt")
        self.assertFalse(os.path.exists(expected_file_path), f"File {expected_file_path} was created in dry run mode")
        
        # Verify that the correct logging message was shown
        mock_logging.info.assert_any_call(f"Dry run: Would add {repo_url} to registry at {expected_file_path}")
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_package_already_exists(self, mock_logging):
        """Test that add_package_to_index does not create a duplicate entry."""
        repo_url = "https://github.com/testorg/testrepo"
        
        # Create the file first
        os.makedirs(os.path.join(self.registry_path, "testorg"), exist_ok=True)
        with open(os.path.join(self.registry_path, "testorg/testrepo.txt"), "w") as f:
            f.write(f"{repo_url}\n")
        
        # Call the method again
        self.registry.add_package_to_index(repo_url)
        
        # Verify that the correct logging message was shown
        mock_logging.info.assert_any_call(f"Package testorg/testrepo is already in the registry. No changes made.")
    
    @patch('zero_infra_mod_registry.registry.filesystem_package_registry.logging')
    def test_add_package_with_different_url_format(self, mock_logging):
        """Test that add_package_to_index handles different URL formats."""
        # Test with trailing slash
        repo_url = "https://github.com/testorg/testrepo/"
        
        # Call the method
        self.registry.add_package_to_index(repo_url)
        
        # Check that the file was created with the correct name
        expected_file_path = os.path.join(self.registry_path, "testorg/testrepo.txt")
        self.assertTrue(os.path.exists(expected_file_path), f"File {expected_file_path} was not created")


if __name__ == "__main__":
    unittest.main()
