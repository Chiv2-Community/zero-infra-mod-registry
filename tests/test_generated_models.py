"""Generation drift and handwritten loading behavior, not schema constraints."""
from pathlib import Path
import subprocess
import sys

import pytest

from mod_registry_core.generated_requests import Action
from mod_registry_core.registration import load_registration_request
from zero_infra_mod_registry.models import Mod
from tests.fakes import mod_fixture


def test_generated_sources_are_current() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "scripts/generate_models.py", "--check"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_timestamp_keeps_release_context() -> None:
    data = mod_fixture().releases[0].asdict()
    data["release_date"] = "not a date"
    with pytest.raises(ValueError, match="release v1.0.0: release_date"):
        Mod.from_dict({"latest_release_info": mod_fixture().latest_release_info.asdict(), "releases": [data]})


def test_issue_request_structures_the_action_enum() -> None:
    request = load_registration_request({"action": "add-dll-release", "repo_url": "https://github.com/Test/Plugin", "release_tag": "v1.0.0"})
    assert request.action is Action.ADD_DLL_RELEASE
    assert request.dll_file is None
