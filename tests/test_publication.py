"""Exercise publication's real Git candidate and CLI validation boundaries."""
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.fakes import FakeRetriever, mod_fixture
from tests.test_dll_registry import DLL
from zero_infra_mod_registry.models import Dependency, Repo
from zero_infra_mod_registry.registry import FilesystemPackageRegistry


@pytest.mark.parametrize("dependent", [True, False])
def test_valid_inputs_require_valid_merged_registry(tmp_path: Path, dependent: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    work = tmp_path / "work"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=work, text=True, capture_output=True, check=True).stdout.strip()

    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    git("checkout", "-b", "main")
    fake = FakeRetriever()
    fake.dll = DLL
    fake.measurement = DLL.sha256, DLL.size
    registry = FilesystemPackageRegistry(fake, str(work / "registry"), str(work / "package_db"), str(work / "dll_db"))
    assert registry.add_dll_release(Repo("Test", "Plugin"), "v1.0.0")
    git("add", ".")
    git("commit", "-m", "Approved plugin")
    git("branch", "db")
    git("push", "origin", "main", "db")
    git("checkout", "db")
    fixture = mod_fixture("Dependent")
    info = replace(fixture.latest_release_info, plugin_dependencies=[Dependency("https://github.com/Test/Plugin", "1.0.0")] if dependent else [])
    fake.releases[("Test/Dependent", "v1.0.0")] = replace(fixture.releases[0], info=info)
    assert registry.add_package_release(Repo("Test", "Dependent"), "v1.0.0")
    assert registry.validate_package_db([]) and registry.validate_dll_db(True)
    git("add", ".")
    git("commit", "-m", "Destination-only approved mod")
    git("push", "origin", "db")
    destination = git("rev-parse", "HEAD")
    git("checkout", "main")
    git("rm", "-r", "dll_db")
    git("commit", "-m", "Source removes plugin")
    git("push", "origin", "main")
    source = git("rev-parse", "HEAD")

    def validate() -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "zero_infra_mod_registry.main", "--github-token", "offline-validation", "validate", "--verify-dll-downloads"], cwd=work, text=True, capture_output=True)

    assert validate().returncode == 0
    output = tmp_path / "output"
    env = os.environ | {"SOURCE_SHA": source, "SOURCE_BRANCH": "main", "TARGET_BRANCH": "db", "GITHUB_REF": "refs/heads/main", "GITHUB_OUTPUT": str(output)}
    subprocess.run(["bash", str(root / "actions/publish-branch/publish.sh")], cwd=work, env=env, check=True, capture_output=True)
    candidate = output.read_text().strip().removeprefix("candidate_sha=")
    assert candidate == git("rev-parse", "HEAD")
    assert git("ls-remote", "origin", "refs/heads/db").split()[0] == destination
    result = validate()
    assert (result.returncode != 0) == dependent
    if result.returncode == 0:
        subprocess.run(["bash", str(root / "actions/publish-branch/push.sh")], cwd=work, env=env | {"CANDIDATE_SHA": candidate}, check=True, capture_output=True)
    assert git("ls-remote", "origin", "refs/heads/db").split()[0] == (destination if dependent else candidate)


def test_publication_workflow_gates_exact_candidate_push() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/publish-registry.yml").read_text()
    prepare = workflow.index("- name: Merge validated snapshot")
    validate = workflow.index("- name: Validate merge candidate")
    push = workflow.index("- name: Publish validated candidate")
    assert prepare < validate < push
    assert "command: validate" in workflow[validate:push]
    assert "verify_dll_downloads: 'true'" in workflow[validate:push]
    assert "CANDIDATE_SHA: ${{ steps.merge.outputs.candidate_sha }}" in workflow[push:]
    assert "run: bash .registry-tool/actions/publish-branch/push.sh" in workflow[push:]
    assert "if:" not in workflow[validate:]
