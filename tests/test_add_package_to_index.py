import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from zero_infra_mod_registry.registry.filesystem_package_registry import FilesystemPackageRegistry

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

if __name__ == '__main__':
    unittest.main()
