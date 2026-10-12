"""Exercise the Dockerfile's actual staged inputs and installed wheel boundary."""
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from zipfile import ZipFile


def test_docker_builder_inputs_produce_wheel_with_usable_schemas(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    context = tmp_path / "build"
    context.mkdir()
    builder = (root / "Dockerfile").read_text().split("RUN uv build --wheel", 1)[0]
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
    result = subprocess.run(["uv", "build", "--wheel"], cwd=context, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    wheel, = (context / "dist").glob("*.whl")
    installed = tmp_path / "installed"
    with ZipFile(wheel) as archive:
        for kind in ("mod", "plugin"):
            assert f"zero_infra_mod_registry/schemas/{kind}.schema.json" in archive.namelist()
        archive.extractall(installed)
    # -I prevents cwd/PYTHONPATH from providing source-tree schemas. Dependencies
    # come from the test environment, but production modules come only from the wheel.
    script = """
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from zero_infra_mod_registry.metadata_validation import validate_metadata
from zero_infra_mod_registry.models.dll_metadata import PluginInfo, PluginTarget
from zero_infra_mod_registry.registry import FilesystemPackageRegistry
from zero_infra_mod_registry.retriever import GithubModMetadataRetriever
from github import Github
registry = FilesystemPackageRegistry(GithubModMetadataRetriever(Github()), 'registry', 'package_db', 'dll_db')
for target in ('server', 'client', 'shared'):
    data = {'name': 'Plugin', 'description': 'Description', 'authors': ['Author'], 'target': target}
    path = Path('plugin.json')
    path.write_text(json.dumps(data))
    validate_metadata(path, 'plugin', registry)
    assert PluginInfo.from_dict(data).target is PluginTarget(target)
path = Path('mod.json')
path.write_text(json.dumps({'name': 'Pak', 'description': 'Description', 'authors': ['Author']}))
validate_metadata(path, 'mod', registry)
"""
    validation = subprocess.run([sys.executable, "-I", "-c", script, str(installed)],
                                cwd=tmp_path, capture_output=True, text=True)
    assert validation.returncode == 0, validation.stderr
