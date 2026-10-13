"""Build and install each workspace package outside the source tree."""
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest


@pytest.fixture(scope="module")
def workspace_wheels(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("workspace-wheels")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["uv", "build", "--wheel", "--all-packages", "--out-dir", str(output)],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(list(output.glob("*.whl"))) == 3
    return output


@pytest.mark.parametrize("package,module,other", [
    ("automated_registry_gateway", "automated_registry_gateway", "zero_infra_mod_registry"),
    ("zero_infra_mod_registry", "zero_infra_mod_registry", "automated_registry_gateway"),
])
def test_component_installs_without_other_component(
    workspace_wheels: Path, tmp_path: Path, package: str, module: str, other: str,
) -> None:
    wheel, = workspace_wheels.glob(f"{package}-*.whl")
    core_wheel, = workspace_wheels.glob("mod_registry_core-*.whl")
    with ZipFile(wheel) as archive:
        assert any(name.startswith(f"{module}/") for name in archive.namelist())
        assert not any(name.startswith(f"{other}/") for name in archive.namelist())
    environment = tmp_path / "venv"
    result = subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    python = environment / "bin/python"
    result = subprocess.run(["uv", "pip", "install", "--python", str(python), str(core_wheel), str(wheel)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    script = """
from importlib.util import find_spec
import sys
assert find_spec(sys.argv[1]) is not None
assert find_spec(sys.argv[2]) is None
from mod_registry_core.json_types import decode_json, json_object
assert json_object(decode_json('{"name":"example"}')) == {'name': 'example'}
if sys.argv[1] == 'automated_registry_gateway':
    from automated_registry_gateway.server import main
else:
    from zero_infra_mod_registry.main import main
assert callable(main)
"""
    result = subprocess.run([str(python), "-I", "-c", script, module, other],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    command = environment / "bin" / package.replace("_", "-")
    help_result = subprocess.run([str(command), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert help_result.returncode == 0, help_result.stderr
