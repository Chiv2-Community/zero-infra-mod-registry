"""Generation drift and handwritten loading behavior, not schema constraints."""
from pathlib import Path
import subprocess
import sys

import pytest

from generated_models.requests import Action
from mod_registry_core.registration import load_registration_request
from generated_models.metadata import Mod
from zero_infra_mod_registry.models.loading import load, serialize
from tests.fakes import mod_fixture


def test_generated_sources_are_current() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "code_gen", "--check"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_timestamp_keeps_release_context() -> None:
    data = serialize(mod_fixture().releases[0])
    data["release_date"] = "not a date"
    with pytest.raises(ValueError, match="release v1.0.0: release_date"):
        load({"latest_release_info": serialize(mod_fixture().latest_release_info), "releases": [data]}, Mod)


def test_issue_request_structures_the_action_enum() -> None:
    request = load_registration_request({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0"})
    assert request.action is Action.ADD_DLL_RELEASE
    assert request.dll_file is None
