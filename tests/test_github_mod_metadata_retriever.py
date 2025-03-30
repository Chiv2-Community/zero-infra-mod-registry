import unittest
from unittest.mock import MagicMock, patch

from zero_infra_mod_registry.models.mod_metadata import Dependency, Mod, Release, Repo
from zero_infra_mod_registry.retriever.github_mod_metadata_retriever import (
    GithubModMetadataRetriever,
)
from zero_infra_mod_registry.retriever.mod_metadata_retriever import (
    VALID_MOD_TYPES,
    VALID_TAGS,
)


class TestGithubModMetadataRetriever(unittest.TestCase):
    def setUp(self):
        # Create a mock Github client
        self.mock_github = MagicMock()
        self.mod_retriever = GithubModMetadataRetriever(self.mock_github)

    def test_validate_tags(self):
        """Test tag validation."""
        # Valid tags
        valid_tags = ["Mutator", "Map", "Cosmetic"]
        self.assertIsNone(self.mod_retriever.validate_tags(valid_tags))

        # Empty tags
        self.assertIsNone(self.mod_retriever.validate_tags([]))

        # Invalid tags
        invalid_tags = ["Mutator", "InvalidTag", "Map"]
        error = self.mod_retriever.validate_tags(invalid_tags)
        self.assertIsNotNone(error)
        self.assertIn("InvalidTag", error)
        self.assertIn(str(VALID_TAGS), error)

    def test_validate_mod_type(self):
        """Test mod type validation."""
        # Valid mod types
        for mod_type in VALID_MOD_TYPES:
            self.assertIsNone(self.mod_retriever.validate_mod_type(mod_type))

        # Invalid mod type
        invalid_mod_type = "InvalidType"
        error = self.mod_retriever.validate_mod_type(invalid_mod_type)
        self.assertIsNotNone(error)
        self.assertIn(invalid_mod_type, error)
        self.assertIn(str(VALID_MOD_TYPES), error)

    def test_validate_version_tag_name(self):
        """Test version tag validation."""
        # Valid version tags
        valid_tags = ["1.0.0", "v1.0.0", "1.2.3-beta.1"]
        for tag in valid_tags:
            self.assertIsNone(self.mod_retriever.validate_version_tag_name(tag))

        # Invalid version tags
        invalid_tags = ["version1", "v"]
        for tag in invalid_tags:
            error = self.mod_retriever.validate_version_tag_name(tag)
            self.assertIsNotNone(error)
            self.assertIn(tag.lstrip("v"), error)

    def test_validate_dependency_versions(self):
        """Test dependency version validation."""
        # Valid dependency versions
        valid_deps = [
            Dependency(repo_url="https://github.com/org/repo", version="1.0.0"),
            Dependency(repo_url="https://github.com/org/repo", version="v1.0.0"),
            Dependency(repo_url="https://github.com/org/repo", version="^1.0.0"),
            Dependency(
                repo_url="https://github.com/org/repo", version=">=1.0.0,<2.0.0"
            ),
        ]
        errors = self.mod_retriever.validate_dependency_versions(valid_deps)
        self.assertEqual(len(errors), 0)

        # Definitely invalid dependency versions
        invalid_deps = [
            Dependency(repo_url="https://github.com/org/repo", version="invalid"),
            Dependency(repo_url="https://github.com/org/repo", version="v"),
        ]
        errors = self.mod_retriever.validate_dependency_versions(invalid_deps)
        self.assertEqual(len(errors), 2)
        for error in errors:
            self.assertIn("does not conform to the semver spec", error)

    @patch("requests.get")
    def test_find_pak_file(self, mock_requests_get):
        """Test finding a pak file in release assets."""
        # Mock a release with a single pak file
        mock_release = MagicMock()
        mock_release.tag_name = "v1.0.0"

        # Mock asset that ends with .pak
        mock_asset1 = MagicMock()
        mock_asset1.name = "mod.pak"

        # Mock asset that doesn't end with .pak
        mock_asset2 = MagicMock()
        mock_asset2.name = "readme.md"

        mock_release.get_assets.return_value = [mock_asset1, mock_asset2]

        # Test finding the pak file
        result = self.mod_retriever.find_pak_file(mock_release)
        self.assertEqual(result, mock_asset1)

        # Test when no pak file exists
        mock_release.get_assets.return_value = [mock_asset2]
        result = self.mod_retriever.find_pak_file(mock_release)
        self.assertIsInstance(result, str)
        self.assertIn("No pak file found", result)

        # Test when multiple pak files exist
        mock_asset3 = MagicMock()
        mock_asset3.name = "mod2.pak"
        mock_release.get_assets.return_value = [mock_asset1, mock_asset3]
        result = self.mod_retriever.find_pak_file(mock_release)
        self.assertIsInstance(result, str)
        self.assertIn("Multiple pak files found", result)

    @patch(
        "zero_infra_mod_registry.retriever.github_mod_metadata_retriever.GithubModMetadataRetriever.process_release"
    )
    def test_fetch_all_releases(self, mock_process_release):
        """Test retrieving all releases for a repository."""
        repo = Repo(org="testorg", name="testrepo")

        # Mock GitHub repo and releases
        mock_github_repo = MagicMock()
        self.mock_github.get_repo.return_value = mock_github_repo

        # Mock releases
        mock_release1 = MagicMock()
        mock_release1.tag_name = "v1.0.0"
        mock_release2 = MagicMock()
        mock_release2.tag_name = "v1.1.0"

        # Set up releases to be returned by get_releases()
        mock_releases = MagicMock()
        mock_releases.totalCount = 2
        mock_releases.__iter__.return_value = [mock_release1, mock_release2]
        mock_github_repo.get_releases.return_value = mock_releases

        # Mock the processed releases
        mock_processed_release1 = MagicMock()
        mock_processed_release1.release_date = "2023-01-01T00:00:00"
        mock_processed_release2 = MagicMock()
        mock_processed_release2.release_date = "2023-02-01T00:00:00"

        # Setup the side effect for process_release
        mock_process_release.side_effect = [
            mock_processed_release1,
            mock_processed_release2,
        ]

        # Call the method
        releases = self.mod_retriever.fetch_all_releases(repo)

        # Verify results
        self.assertEqual(len(releases), 2)
        self.mock_github.get_repo.assert_called_once_with("testorg/testrepo")
        mock_github_repo.get_releases.assert_called_once()

        # Verify process_release was called for each release
        self.assertEqual(mock_process_release.call_count, 2)
        mock_process_release.assert_any_call(repo, mock_release1)
        mock_process_release.assert_any_call(repo, mock_release2)

    def test_update_mod_with_release(self):
        """Test updating a mod with a new release."""
        # Create a mock mod with existing releases
        mock_manifest1 = MagicMock()
        mock_release1 = MagicMock()
        mock_release1.tag = "v1.0.0"
        mock_release1.release_date = "2023-01-01T00:00:00"
        mock_release1.manifest = mock_manifest1

        mock_manifest2 = MagicMock()
        mock_release2 = MagicMock()
        mock_release2.tag = "v1.1.0"
        mock_release2.release_date = "2023-02-01T00:00:00"
        mock_release2.manifest = mock_manifest2

        mock_mod = MagicMock(spec=Mod)
        mock_mod.releases = [mock_release1, mock_release2]
        mock_mod.latest_manifest = mock_manifest2

        # Create a new release to add
        mock_manifest3 = MagicMock()
        mock_release3 = MagicMock(spec=Release)
        mock_release3.tag = "v1.2.0"
        mock_release3.release_date = "2023-03-01T00:00:00"
        mock_release3.manifest = mock_manifest3

        # Update the mod with the new release
        updated_mod = self.mod_retriever.update_mod_with_release(
            mock_mod, mock_release3
        )

        # Verify the updated mod has all three releases
        self.assertEqual(len(updated_mod.releases), 3)
        self.assertIn(mock_release1, updated_mod.releases)
        self.assertIn(mock_release2, updated_mod.releases)
        self.assertIn(mock_release3, updated_mod.releases)

        # Verify the latest manifest is from the newest release
        self.assertEqual(updated_mod.latest_manifest, mock_manifest3)

    @patch("requests.get")
    def test_fetch_release_metadata(self, mock_requests_get):
        """Test fetching metadata for a specific release."""
        # Create a mock mod
        mock_manifest = MagicMock()
        mock_manifest.repo_url = "https://github.com/testorg/testrepo"
        mock_mod = MagicMock(spec=Mod)
        mock_mod.latest_manifest = mock_manifest

        # Mock the GitHub repo and release
        mock_github_repo = MagicMock()
        self.mock_github.get_repo.return_value = mock_github_repo

        mock_release = MagicMock()
        mock_release.tag_name = "v1.2.0"
        mock_github_repo.get_release.return_value = mock_release

        # Mock the process_release method to return a release
        mock_processed_release = MagicMock(spec=Release)
        with patch.object(
            self.mod_retriever, "process_release", return_value=mock_processed_release
        ):
            # Call the method
            release = self.mod_retriever.fetch_release_metadata(mock_mod, "v1.2.0")

            # Verify results
            self.assertEqual(release, mock_processed_release)
            self.mock_github.get_repo.assert_called_once_with("testorg/testrepo")
            mock_github_repo.get_release.assert_called_once_with("v1.2.0")
            self.mod_retriever.process_release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
