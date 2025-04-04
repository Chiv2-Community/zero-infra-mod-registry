import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zero_infra_mod_registry.models import Manifest, Mod, Release, Repo
from zero_infra_mod_registry.registry.filesystem_package_registry import (
    FilesystemPackageRegistry,
)
from zero_infra_mod_registry.retriever.mod_metadata_retriever import (
    ModMetadataRetriever,
)
from zero_infra_mod_registry.utils.path_utils import repo_to_index_entry


class TestFilesystemPackageRegistryBase(unittest.TestCase):
    """Base class for FilesystemPackageRegistry tests providing common setup and teardown."""
    
    def setUp(self):
        """Set up a test environment with temporary directories and mock objects."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.test_dir, "registry")
        self.package_db_path = os.path.join(self.test_dir, "package_db")

        # Create test directories
        os.makedirs(self.registry_path, exist_ok=True)
        os.makedirs(self.package_db_path, exist_ok=True)

        # Create a mock mod retriever
        self.mock_retriever = MagicMock(spec=ModMetadataRetriever)

        # Create the registry instance
        self.registry = FilesystemPackageRegistry(
            mod_retriever=self.mock_retriever,
            registry_path=self.registry_path,
            package_db_path=self.package_db_path,
        )

    def tearDown(self):
        """Clean up test environment by removing temporary directories."""
        shutil.rmtree(self.test_dir)


class TestFilesystemPackageRegistryCoreFunctions(TestFilesystemPackageRegistryBase):
    """Tests for the core file processing and utilities in FilesystemPackageRegistry."""
    
    def setUp(self):
        """Set up test files for core functionality testing."""
        super().setUp()
        # Create redirects directory
        os.makedirs(os.path.join(self.registry_path, "redirects"), exist_ok=True)
        
        # Create test files
        with open(os.path.join(self.registry_path, "org1.txt"), "w") as f:
            f.write("https://github.com/org1/repo1\n")
            f.write("# This is a comment\n")
            f.write("https://github.com/org1/repo2\n")
            f.write("\n")  # Empty line

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
        lines = self.registry._get_all_text_lines_in_directory(self.registry_path)

        # We should have 2 non-empty, non-comment lines in total
        self.assertEqual(len(lines), 2)
        self.assertIn("https://github.com/org1/repo1", lines)
        self.assertIn("https://github.com/org1/repo2", lines)

        # Ensure comments and empty lines are ignored
        self.assertNotIn("# This is a comment", lines)
        self.assertNotIn("", lines)

    def test_generate_package_list(self):
        """Test generating a package list from a directory."""
        packages = self.registry._generate_package_list(self.registry_path)
        self.assertEqual(len(packages), 2)
        self.assertIn("org1/repo1", packages)
        self.assertIn("org1/repo2", packages)

    def test_repo_to_index_entry(self):
        """Test the repo_to_index_entry function."""
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

    def test_is_package_initialized(self):
        """Test the is_package_initialized method."""
        # Create a mock package file
        os.makedirs(
            os.path.join(self.package_db_path, "packages", "testorg"), exist_ok=True
        )
        with open(
            os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json"), "w"
        ) as f:
            f.write('{"dummy": "data"}')

        # Test with an initialized package
        self.assertTrue(self.registry.is_package_initialized("testorg", "testrepo"))

        # Test with a non-initialized package
        self.assertFalse(self.registry.is_package_initialized("nonexistent", "repo"))


class TestModOperations(TestFilesystemPackageRegistryBase):
    """Tests for loading, validating, and manipulating mod data."""
    
    def setUp(self):
        """Set up environment for mod operation tests."""
        super().setUp()
        os.makedirs(os.path.join(self.package_db_path, "packages"), exist_ok=True)
        
        # Create the mod_list_index.txt file
        self.mod_list_index_path = os.path.join(
            self.package_db_path, "mod_list_index.txt"
        )
        with open(self.mod_list_index_path, "w") as f:
            f.write("testorg/testrepo\n")
            
        # Test repos
        self.test_repo = Repo("testorg", "testrepo")
        self.nonexistent_repo = Repo("nonexistent", "repo")

    @patch("builtins.open")
    def test_load_mod(self, mock_open):
        """Test load_mod method."""
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = '{"name": "test-mod", "releases": []}'

        with patch("json.loads") as mock_loads, patch(
            "zero_infra_mod_registry.models.Mod.from_dict"
        ) as mock_from_dict:
            mock_loads.return_value = {"name": "test-mod", "releases": []}
            mock_mod = MagicMock(spec=Mod)
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

    def test_validate_package_db_empty(self):
        """Test validate_package_db with empty additional_mods."""
        # Just testing that it runs without exceptions
        self.registry.validate_package_db([])


class TestPackageRegistryUpdates(TestFilesystemPackageRegistryBase):
    """Tests for registry update process and validation functionality."""
    
    def setUp(self):
        """Set up environment for registry update tests."""
        super().setUp()
        os.makedirs(os.path.join(self.registry_path, "redirects"), exist_ok=True)
        os.makedirs(os.path.join(self.package_db_path, "packages"), exist_ok=True)

    def test_process_registry_updates_with_dry_run(self):
        """Test process_registry_updates with dry_run=True."""
        # Prepare mock and setup
        with patch.object(self.registry, "add_package") as mock_init, patch.object(
            self.registry, "remove_mods"
        ) as mock_remove_mods:
            # Configure return values for the mocked methods
            mock_init.return_value = 1
            mock_remove_mods.return_value = 1
            
            # Create an existing mod_list_index.txt with different content
            with open(self.registry.mod_list_index_path, "w") as f:
                f.write("org1/old_repo\n")
            
            # Create a new repo entry in the registry dir to trigger the init call
            os.makedirs(os.path.join(self.registry_path, "org2"), exist_ok=True)
            with open(os.path.join(self.registry_path, "org2/new_repo.txt"), "w") as f:
                f.write("https://github.com/org2/new_repo\n")
            
            # Mock _generate_package_list to return predictable results
            with patch.object(self.registry, "_generate_package_list") as mock_generate_package_list:
                mock_generate_package_list.return_value = ["org2/new_repo"]
                
                # Run with dry_run=True
                result = self.registry.process_registry_updates(dry_run=True)
                
                # Verify that the method returns True (successful update)
                self.assertTrue(result, "process_registry_updates should return True on successful update")

                # Verify the correct methods were called with dry_run=True
                mock_init.assert_called_once()
                args, kwargs = mock_init.call_args
                self.assertEqual(len(args), 2)
                self.assertTrue(isinstance(args[0], list))
                self.assertTrue(args[1])  # dry_run should be True
                
                mock_remove_mods.assert_called_once()
                args, kwargs = mock_remove_mods.call_args
                self.assertEqual(len(args), 2)
                self.assertTrue(isinstance(args[0], list))
                self.assertTrue(args[1])  # dry_run should be True

                # Verify mod_list_index.txt was not updated
                with open(self.registry.mod_list_index_path, "r") as f:
                    content = f.read().strip()
                    self.assertEqual(content, "org1/old_repo")


class TestAddRelease(TestFilesystemPackageRegistryBase):
    """Tests for the add_package_release functionality."""

    def setUp(self):
        """Set up test environment for add_release tests."""
        super().setUp()
        # Create packages directory
        os.makedirs(os.path.join(self.package_db_path, "packages"), exist_ok=True)

        # Create the mod_list_index.txt file
        self.mod_list_index_path = os.path.join(
            self.package_db_path, "mod_list_index.txt"
        )
        with open(self.mod_list_index_path, "w") as f:
            f.write("testorg/testrepo\n")

        # Test repos
        self.test_repo = Repo("testorg", "testrepo")
        self.nonexistent_repo = Repo("nonexistent", "repo")

    def test_add_release_fails_if_package_not_in_index(self):
        """Test that add_package_release fails if the package is not in the package list."""
        with self.assertRaises(ValueError) as context:
            self.registry.add_package_release(self.nonexistent_repo, "v1.0.0")

        self.assertIn("not in the package list", str(context.exception))

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_add_release_initializes_if_mod_not_found(self, mock_logging):
        """Test that add_package_release initializes the repo if the mod is not found."""
        # Mock the load_mod method to return None
        self.registry.load_mod = MagicMock(return_value=None)
        self.registry.add_package = MagicMock(return_value=1)

        # Call add_package_release
        result = self.registry.add_package_release(self.test_repo, "v1.0.0")

        # Verify that the method returns the result of add_package
        self.assertEqual(result, 1, "add_package_release should return the result of add_package when initializing")

        # Verify that the correct methods were called
        self.registry.load_mod.assert_called_once_with(self.test_repo)
        self.registry.add_package.assert_called_once_with([self.test_repo], False)

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_add_release_fetches_release_metadata(self, mock_logging):
        """Test that add_package_release fetches release metadata for new releases."""
        # Create a mock mod
        mock_mod = MagicMock(spec=Mod)
        mock_mod.releases = []

        # Mock the load_mod method to return our mock mod
        self.registry.load_mod = MagicMock(return_value=mock_mod)

        # Mock the fetch_release_metadata method
        mock_release = MagicMock(spec=Release)
        self.mock_retriever.fetch_release_metadata = MagicMock(
            return_value=mock_release
        )

        # Mock update_mod_with_release
        updated_mod = MagicMock(spec=Mod)
        self.mock_retriever.update_mod_with_release = MagicMock(
            return_value=updated_mod
        )

        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()

        # Call add_package_release
        result = self.registry.add_package_release(self.test_repo, "v1.0.0", dry_run=True)
        
        # Verify that the method returns 1 (success)
        self.assertEqual(result, 1, "add_package_release should return 1 on successful addition")

        # Verify that the correct methods were called
        self.mock_retriever.fetch_release_metadata.assert_called_once_with(
            mock_mod, "v1.0.0"
        )
        self.mock_retriever.update_mod_with_release.assert_called_once_with(
            mock_mod, mock_release
        )
        self.registry.validate_package_db.assert_called_once_with([updated_mod])
    
    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_add_release_skips_existing_tag(self, mock_logging):
        """Test that add_package_release skips if the release tag already exists."""
        # Create a mock mod with an existing release
        mock_release = MagicMock(spec=Release)
        mock_release.tag = "v1.0.0"
        
        mock_mod = MagicMock(spec=Mod)
        mock_mod.releases = [mock_release]

        # Mock the load_mod method to return our mock mod
        self.registry.load_mod = MagicMock(return_value=mock_mod)

        # Call add_package_release with the existing tag
        result = self.registry.add_package_release(self.test_repo, "v1.0.0")

        # Verify that the method returns 0 (no releases added)
        self.assertEqual(result, 0, "add_package_release should return 0 when skipping existing tags")

        # Verify that fetch_release_metadata was not called
        self.mock_retriever.fetch_release_metadata.assert_not_called()
        
        # Verify warning was logged
        mock_logging.warning.assert_any_call(f"Release v1.0.0 already exists in repo {self.test_repo}.")


class TestRepositoryInitialization(TestFilesystemPackageRegistryBase):
    """Tests for the add_package functionality."""

    def setUp(self):
        """Set up test environment for init tests."""
        super().setUp()
        # Create packages directory
        os.makedirs(os.path.join(self.package_db_path, "packages"), exist_ok=True)
        
        # Test repo
        self.repo_url = "https://github.com/testorg/testrepo"
        self.test_repo = Repo("testorg", "testrepo")
        
        # Create mock mod for testing
        self.mock_mod = MagicMock(spec=Mod)
        self.mock_mod.latest_manifest = MagicMock(spec=Manifest)
        self.mock_mod.latest_manifest.repo_url = self.repo_url
        self.mock_mod.asdict = MagicMock(return_value={"name": "test-mod", "releases": []})
        
        # Configure mock retriever by default
        self.mock_retriever.fetch_repo_metadata = MagicMock(return_value=self.mock_mod)

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_init_creates_package_file_and_registry_entry(self, mock_logging):
        """Test that add_package creates both a package file and a registry entry."""
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call add_package
        result = self.registry.add_package([self.test_repo])
        
        # Verify that the method returns the number of successfully initialized repos
        self.assertEqual(result, 1, "add_package should return the number of successfully initialized repos")
        
        # Verify that the package file was created
        package_file_path = os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json")
        self.assertTrue(os.path.exists(package_file_path), f"Package file {package_file_path} was not created")
        
        # Verify that the registry entry was created
        registry_file_path = os.path.join(self.registry_path, "testorg", "testrepo.txt")
        self.assertTrue(os.path.exists(registry_file_path), f"Registry file {registry_file_path} was not created")
        
        # Check the content of the registry file
        with open(registry_file_path, "r") as f:
            content = f.read().strip()
            self.assertEqual(content, self.repo_url)
    
    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_init_dry_run(self, mock_logging):
        """Test that add_package in dry run mode doesn't create files."""
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call add_package in dry run mode
        result = self.registry.add_package([self.test_repo], dry_run=True)
        
        # Verify that the method returns the number of repos that would be initialized
        self.assertEqual(result, 1, "add_package should return the number of repos that would be initialized")
        
        # Verify that no files were created
        package_file_path = os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json")
        self.assertFalse(os.path.exists(package_file_path), f"Package file {package_file_path} was created in dry run mode")
        
        registry_file_path = os.path.join(self.registry_path, "testorg", "testrepo.txt")
        self.assertFalse(os.path.exists(registry_file_path), f"Registry file {registry_file_path} was created in dry run mode")
        
        # Verify that the dry run warning was logged
        mock_logging.warning.assert_any_call("Dry run; not writing to package dir or registry.")
    
    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_init_with_existing_registry_entry(self, mock_logging):
        """Test that add_package doesn't create a duplicate registry entry."""
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Create the registry entry first
        os.makedirs(os.path.join(self.registry_path, "testorg"), exist_ok=True)
        with open(os.path.join(self.registry_path, "testorg/testrepo.txt"), "w") as f:
            f.write(f"{self.repo_url}\n")
        
        # Call add_package
        self.registry.add_package([self.test_repo])
        
        # Verify that the package file was created
        package_file_path = os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json")
        self.assertTrue(os.path.exists(package_file_path), f"Package file {package_file_path} was not created")
        
        # Check if logging indicates the entry already exists
        found_log = False
        for call in mock_logging.info.call_args_list:
            args, _ = call
            if len(args) > 0 and "already exists" in args[0] and "testorg/testrepo" in args[0]:
                found_log = True
                break
        
        self.assertTrue(found_log, "Did not log that the registry entry already exists")

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_init_with_failed_repo_metadata_fetch(self, mock_logging):
        """Test that add_package handles failed repository metadata fetches."""
        # Mock the fetch_repo_metadata method to return None
        self.mock_retriever.fetch_repo_metadata = MagicMock(return_value=None)
        
        # Call add_package
        result = self.registry.add_package([self.test_repo])
        
        # Verify that the method returns 0 (no repos initialized)
        self.assertEqual(result, 0, "add_package should return 0 when no repos are initialized")
        
        # Verify that no files were created
        package_file_path = os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json")
        self.assertFalse(os.path.exists(package_file_path), f"Package file {package_file_path} was created despite fetch failure")
        
        registry_file_path = os.path.join(self.registry_path, "testorg", "testrepo.txt")
        self.assertFalse(os.path.exists(registry_file_path), f"Registry file {registry_file_path} was created despite fetch failure")
        
        # Verify that the correct error log was shown
        mock_logging.error.assert_any_call("Failed to initialize some repos.")
    
    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_init_multiple_repos(self, mock_logging):
        """Test that add_package can initialize multiple repositories at once."""
        # Create test repos
        test_repo1 = Repo("org1", "repo1")
        test_repo2 = Repo("org2", "repo2")
        
        # Create mock mods
        mock_mod1 = MagicMock(spec=Mod)
        mock_mod1.latest_manifest = MagicMock(spec=Manifest)
        mock_mod1.latest_manifest.repo_url = "https://github.com/org1/repo1"
        mock_mod1.asdict = MagicMock(return_value={"name": "mod1", "releases": []})
        
        mock_mod2 = MagicMock(spec=Mod)
        mock_mod2.latest_manifest = MagicMock(spec=Manifest)
        mock_mod2.latest_manifest.repo_url = "https://github.com/org2/repo2"
        mock_mod2.asdict = MagicMock(return_value={"name": "mod2", "releases": []})
        
        # Mock the fetch_repo_metadata method
        self.mock_retriever.fetch_repo_metadata = MagicMock(side_effect=[mock_mod1, mock_mod2])
        
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call add_package with multiple repos
        result = self.registry.add_package([test_repo1, test_repo2])
        
        # Verify that the method returns the number of successfully initialized repos
        self.assertEqual(result, 2, "add_package should return the number of successfully initialized repos")
        
        # Verify that both package files were created
        package_file_path1 = os.path.join(self.package_db_path, "packages", "org1", "repo1.json")
        package_file_path2 = os.path.join(self.package_db_path, "packages", "org2", "repo2.json")
        self.assertTrue(os.path.exists(package_file_path1), f"Package file {package_file_path1} was not created")
        self.assertTrue(os.path.exists(package_file_path2), f"Package file {package_file_path2} was not created")
        
        # Verify that both registry entries were created
        registry_file_path1 = os.path.join(self.registry_path, "org1", "repo1.txt")
        registry_file_path2 = os.path.join(self.registry_path, "org2", "repo2.txt")
        self.assertTrue(os.path.exists(registry_file_path1), f"Registry file {registry_file_path1} was not created")
        self.assertTrue(os.path.exists(registry_file_path2), f"Registry file {registry_file_path2} was not created")
        
        # Verify the success log
        mock_logging.info.assert_any_call("Successfully initialized all repos.")


class TestRemoveMods(TestFilesystemPackageRegistryBase):
    """Tests for the mod removal functionality."""

    def setUp(self):
        """Set up test environment for remove_mods tests."""
        super().setUp()
        # Create packages directory
        os.makedirs(os.path.join(self.package_db_path, "packages", "testorg"), exist_ok=True)
        
        # Create test file
        with open(os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json"), "w") as f:
            f.write('{"name": "test-mod", "releases": []}')
        
        # Test repo
        self.test_repo = Repo("testorg", "testrepo")
        self.nonexistent_repo = Repo("nonexistent", "repo")

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_remove_mods(self, mock_logging):
        """Test removing a mod."""
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call remove_mods
        result = self.registry.remove_mods([self.test_repo])
        
        # Verify that the method returns the number of removed mods
        self.assertEqual(result, 1, "remove_mods should return the number of successfully removed mods")
        
        # Verify that the package file was removed
        package_file_path = os.path.join(self.package_db_path, "packages", "testorg", "testrepo.json")
        self.assertFalse(os.path.exists(package_file_path), f"Package file {package_file_path} was not removed")
        
        # Verify that the org directory was removed since it's empty
        org_dir = os.path.join(self.package_db_path, "packages", "testorg")
        self.assertFalse(os.path.exists(org_dir), f"Org directory {org_dir} was not removed")
        
        # Verify the success log
        mock_logging.info.assert_any_call("Successfully removed 1 mods.")

    @patch("zero_infra_mod_registry.registry.filesystem_package_registry.logging")
    def test_remove_nonexistent_mod(self, mock_logging):
        """Test removing a mod that doesn't exist."""
        # Mock validate_package_db
        self.registry.validate_package_db = MagicMock()
        
        # Call remove_mods
        result = self.registry.remove_mods([self.nonexistent_repo])
        
        # Verify that the method returns 0 (no mods removed)
        self.assertEqual(result, 0, "remove_mods should return 0 when no mods are removed")
        
        # Verify the warning log
        mock_logging.warning.assert_any_call(f"Mod file for {self.nonexistent_repo} not found at {os.path.join(self.package_db_path, 'packages', 'nonexistent', 'repo.json')}")


if __name__ == "__main__":
    unittest.main()
