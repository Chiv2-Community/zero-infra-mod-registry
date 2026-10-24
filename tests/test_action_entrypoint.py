"""Keep Docker-generated registry paths writable by subsequent runner steps."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("workspace", [True, False])
def test_entrypoint_preserves_arguments_and_status(
    tmp_path: Path, exit_code: int, workspace: bool,
) -> None:
    command = tmp_path / "zero-infra-mod-registry"
    command.write_text(
        '#!/usr/bin/env python\nimport json, sys\n'
        f'print(json.dumps(sys.argv[1:]))\nsys.exit({exit_code})\n'
    )
    command.chmod(0o755)
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(Path(__file__).resolve().parents[1] / "github-action-entrypoint.sh"),
         "add-package-release", "", "repo with spaces", "v1.0.0"],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
             "GITHUB_WORKSPACE": str(tmp_path) if workspace else "", "GITHUB_OUTPUT": str(output),
             "GITHUB_STEP_SUMMARY": ""},
        capture_output=True, text=True,
    )
    assert result.returncode == exit_code, result.stderr
    assert result.stdout.strip() == '["add-package-release", "repo with spaces", "v1.0.0"]'
    assert f"failed={'true' if exit_code else 'false'}" in output.read_text()


@pytest.mark.skipif(not os.environ.get("REGISTRY_DOCKER_TEST_IMAGE"),
                    reason="Set REGISTRY_DOCKER_TEST_IMAGE to run the Docker ownership regression")
@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("root", [True, False])
def test_docker_generated_directories_allow_git_checkout(
    tmp_path: Path, exit_code: int, root: bool,
) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "--allow-empty", "-m", "Base")
    command = tmp_path / "zero-infra-mod-registry"
    command.write_text(
        '#!/usr/bin/env python\nfrom pathlib import Path\nimport sys\n'
        'path = Path("package_db/packages/chivned/AldmereHardpoint.json")\n'
        'path.parent.mkdir(parents=True)\npath.write_text("{}")\n'
        f'sys.exit({exit_code})\n'
    )
    command.chmod(0o755)
    entrypoint = Path(__file__).resolve().parents[1] / "github-action-entrypoint.sh"
    result = subprocess.run([
        "docker", "run", "--rm", "--user", "0:0" if root else f"{os.getuid()}:{os.getgid()}",
        "-v", f"{tmp_path}:/github/workspace", "-v", f"{entrypoint}:/entrypoint.sh:ro",
        "-w", "/github/workspace", "-e", "GITHUB_WORKSPACE=/github/workspace",
        "-e", "PATH=/github/workspace:/usr/local/bin:/usr/bin:/bin",
        "-e", "GITHUB_OUTPUT=/github/workspace/output", "--entrypoint", "bash",
        os.environ["REGISTRY_DOCKER_TEST_IMAGE"], "/entrypoint.sh", "add-package-release",
    ], capture_output=True, text=True)
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert f"failed={'true' if exit_code else 'false'}" in (tmp_path / "output").read_text()
    path = tmp_path / "package_db/packages/chivned/AldmereHardpoint.json"
    assert path.stat().st_uid == os.getuid()
    assert path.parent.stat().st_uid == os.getuid()
    assert path.parent.stat().st_gid == os.getgid()
    git("add", "package_db")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-m", "Register release")
    git("branch", "registration")
    git("checkout", "HEAD~1")
    assert not path.exists()
    git("checkout", "registration")
    assert path.exists()
