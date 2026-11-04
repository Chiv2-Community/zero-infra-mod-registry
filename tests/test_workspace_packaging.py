"""Build and install each workspace package outside the source tree."""
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest


@pytest.fixture(scope="module")
def workspace_wheels(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("workspace-wheels")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["uv", "build", "--all-packages", "--out-dir", str(output)],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(list(output.glob("*.whl"))) == 5
    return output


def test_request_schema_is_bundled_from_the_root_source(workspace_wheels: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "packages/generated-models/src/generated_models/schemas").exists()
    wheel, = workspace_wheels.glob("generated_models-*.whl")
    with ZipFile(wheel) as archive:
        for schema in (root / "schemas").glob("*.schema.json"):
            assert archive.read(f"generated_models/schemas/{schema.name}") == schema.read_bytes()


def test_generated_models_sdist_builds_with_its_own_schemas(workspace_wheels: Path, tmp_path: Path) -> None:
    source, = workspace_wheels.glob("generated_models-*.tar.gz")
    result = subprocess.run(["uv", "build", "--wheel", str(source), "--out-dir", str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original, = workspace_wheels.glob("generated_models-*.whl")
    rebuilt, = tmp_path.glob("generated_models-*.whl")
    with ZipFile(original) as before, ZipFile(rebuilt) as after:
        for name in before.namelist():
            if name.startswith("generated_models/"):
                assert after.read(name) == before.read(name)


def test_codegen_wheel_includes_loading_template(workspace_wheels: Path) -> None:
    wheel, = workspace_wheels.glob("code_gen-*.whl")
    with ZipFile(wheel) as archive:
        assert b"__SCHEMA_BINDINGS__" in archive.read("code_gen/loading.py.tmpl")
        assert b"def decode_json" in archive.read("code_gen/json_types.py.tmpl")


def test_gateway_image_inputs_bundle_the_request_schema(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    context = tmp_path / "build"
    context.mkdir()
    builder = (root / "docker/automated-registry-gateway/Dockerfile").read_text().split("RUN uv sync", 1)[0]
    for line in builder.splitlines():
        if not line.startswith("COPY ") or "--from=" in line:
            continue
        *sources, destination = shlex.split(line)[1:]
        for source in sources:
            original = root / source
            target = context / destination
            if original.is_dir():
                shutil.copytree(original, target)
            else:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target / original.name)
    result = subprocess.run(["uv", "sync", "--frozen", "--no-dev", "--no-editable", "--package", "automated-registry-gateway"],
                            cwd=context, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    script = """
import json
from mod_registry_registration_core.issue_requests import parse_registration_payload, registration_payload
request = registration_payload('mod', 'Test/Pak', 'v1.0.0', 'Pak.pak')
assert parse_registration_payload('```json\\n' + json.dumps(request) + '\\n```') == request
"""
    result = subprocess.run([str(context / ".venv/bin/python"), "-I", "-c", script],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("package,module,other", [
    ("automated_registry_gateway", "automated_registry_gateway", "zero_infra_mod_registry"),
    ("zero_infra_mod_registry", "zero_infra_mod_registry", "automated_registry_gateway"),
])
def test_component_installs_without_other_component(
    workspace_wheels: Path, tmp_path: Path, package: str, module: str, other: str,
) -> None:
    wheel, = workspace_wheels.glob(f"{package}-*.whl")
    core_wheel, = workspace_wheels.glob("mod_registry_registration_core-*.whl")
    models_wheel, = workspace_wheels.glob("generated_models-*.whl")
    with ZipFile(wheel) as archive:
        assert any(name.startswith(f"{module}/") for name in archive.namelist())
        assert not any(name.startswith(f"{other}/") for name in archive.namelist())
    environment = tmp_path / "venv"
    result = subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    python = environment / "bin/python"
    result = subprocess.run(["uv", "pip", "install", "--python", str(python), str(models_wheel), str(core_wheel), str(wheel)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    script = """
from importlib.util import find_spec
import sys
assert find_spec(sys.argv[1]) is not None
assert find_spec(sys.argv[2]) is None
from generated_models.json_types import decode_json, json_object
assert json_object(decode_json('{"name":"example"}')) == {'name': 'example'}
from mod_registry_registration_core.issue_requests import registration_payload
from mod_registry_registration_core.release_assets import selected_dll_name, single_pak_name
assert registration_payload('mod', 'Test/Pak', 'v1.0.0', 'Pak.pak')['release_tag'] == 'v1.0.0'
assert selected_dll_name(['Plugin.dll']) == 'Plugin.dll'
assert single_pak_name(['Pak.pak'], 'v1.0.0') == 'Pak.pak'
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


def test_generated_models_install_without_consumers(workspace_wheels: Path, tmp_path: Path) -> None:
    wheel, = workspace_wheels.glob("generated_models-*.whl")
    environment = tmp_path / "venv"
    result = subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    python = environment / "bin/python"
    result = subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    script = """
from importlib.util import find_spec
from dataclasses import is_dataclass
from generated_models.dependencies import Dependency
from generated_models.metadata import ModInfo
from generated_models.requests import Action, RegistrationRequest
from generated_models.loading import JsonCodec, dumps, loads, load, serialize
from generated_models.json_types import decode_json, json_object
assert is_dataclass(ModInfo) and is_dataclass(RegistrationRequest)
assert ModInfo('https://github.com/Test/Pak', 'Pak', 'Description', ['Author']).mod_dependencies == []
assert RegistrationRequest(Action.ADD_DLL_RELEASE, 'https://github.com/Test/Plugin', 'v1.0.0').dll_file is None
assert Dependency('https://github.com/Test/Pak', '^1.0.0').version == '^1.0.0'
request = load({'action':'add-dll-release', 'repo_url':'https://github.com/Test/Plugin', 'release_tag':'v1.0.0'}, RegistrationRequest)
assert request.action is Action.ADD_DLL_RELEASE
assert serialize(request)['release_tag'] == 'v1.0.0'
assert loads(dumps(request), RegistrationRequest) == request
assert json_object(decode_json(dumps(request))) == serialize(request)
codec = JsonCodec()
checked = []
codec.register_validator(RegistrationRequest, checked.append)
assert codec.loads(codec.dumps(request), RegistrationRequest) == request
assert checked == [request]
try:
    load({'action':'bogus'}, RegistrationRequest)
except ValueError as error:
    assert '$.action' in str(error)
else:
    raise AssertionError('Structural validation was skipped')
for module in ('zero_infra_mod_registry', 'mod_registry_registration_core', 'automated_registry_gateway', 'datamodel_code_generator'):
    assert find_spec(module) is None
"""
    result = subprocess.run([str(python), "-I", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
