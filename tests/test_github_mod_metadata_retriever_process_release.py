import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import json
from datetime import datetime
from zero_infra_mod_registry.retriever.github_mod_metadata_retriever import GithubModMetadataRetriever
from zero_infra_mod_registry.models.mod_metadata import Repo

class TestGithubModMetadataRetrieverProcessRelease(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"}):
            self.retriever = GithubModMetadataRetriever()

    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.requests.get")
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.subprocess.run")
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.os.path.exists")
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.os.listdir")
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.open", new_callable=mock_open)
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.shutil.copyfileobj")
    def test_process_release_success(self, mock_copyfileobj, mock_file_open, mock_listdir, mock_path_exists, mock_subprocess_run, mock_requests_get):
        repo = Repo(org="testorg", name="testrepo")
        mock_release = MagicMock()
        mock_release.tag_name = "v1.0.0"
        mock_release.body = "Release notes"
        
        mock_pak_asset = MagicMock()
        mock_pak_asset.name = "test.pak"
        mock_pak_asset.browser_download_url = "http://example.com/test.pak"
        mock_pak_asset.updated_at = datetime(2023, 1, 1)
        mock_release.get_assets.return_value = [mock_pak_asset]

        mock_response_mod_json = MagicMock()
        mock_response_mod_json.status_code = 200
        mock_response_mod_json.json.return_value = {
            "name": "Test Mod",
            "description": "Description",
            "authors": ["Author"],
            "dependencies": []
        }
        
        mock_response_pak = MagicMock()
        mock_response_pak.status_code = 200
        mock_response_pak.__enter__.return_value = mock_response_pak
        
        mock_requests_get.side_effect = [mock_response_mod_json, mock_response_pak]

        mock_path_exists.return_value = True
        
        mock_listdir.return_value = ["test.pak.json"]
        
        scanner_output = {
            "paks": [
                {
                    "pak_name": "test.pak",
                    "pak_path": "test.pak",
                    "pak_hash": "abc123hash",
                    "inventory": {
                        "markers": [],
                        "blueprints": [],
                        "maps": [],
                        "replacements": [],
                        "arbitrary": []
                    }
                }
            ]
        }

        # We need to handle multiple open calls.
        # 1st: write pak file
        # 2nd: read scanner output JSON
        mock_file_open.side_effect = [
            mock_open().return_value, # for pak file
            mock_open(read_data=json.dumps(scanner_output)).return_value # for scanner output
        ]

        release = self.retriever.process_release(repo, mock_release)

        self.assertEqual(release.tag, "v1.0.0")
        self.assertEqual(release.hash, "abc123hash")
        self.assertEqual(release.info.name, "Test Mod")
        mock_subprocess_run.assert_called_once()
        
    @patch("zero_infra_mod_registry.retriever.github_mod_metadata_retriever.requests.get")
    def test_process_release_no_mod_json(self, mock_requests_get):
        repo = Repo(org="testorg", name="testrepo")
        mock_release = MagicMock()
        mock_release.tag_name = "v1.0.0"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests_get.return_value = mock_response
        
        with self.assertRaisesRegex(Exception, "mod.json does not exist"):
            self.retriever.process_release(repo, mock_release)

if __name__ == "__main__":
    unittest.main()
