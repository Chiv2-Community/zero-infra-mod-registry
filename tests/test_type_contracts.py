"""Guard the strict configuration and prevent broad type escape hatches."""
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_no_dynamic_types_or_type_suppression() -> None:
    for directory in (ROOT / "src", ROOT / "tests"):
        for path in directory.rglob("*.py"):
            text = path.read_text()
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    assert node.id not in {"Any", "object", "Object"}, f"{path}:{node.lineno}"
                elif isinstance(node, ast.Attribute):
                    assert node.attr not in {"Any", "object", "Object"}, f"{path}:{node.lineno}"
            assert "# type:" + " ignore" not in text, path
            assert "# my" + "py:" not in text, path


def test_checker_rejects_untyped_functions_and_dynamic_json(tmp_path: Path) -> None:
    fixture = tmp_path / "invalid_types.py"
    fixture.write_text(
        "import json\n"
        "from typing import Any\n"
        "def untyped(value):\n"
        "    return value\n"
        "explicit: Any = 1\n"
        "unparameterized: dict = {}\n"
        "implicit = json.loads('{}')\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", str(ROOT / "pyproject.toml"),
         "--cache-dir", str(tmp_path / "cache"), str(fixture)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    for code in ("[no-untyped-def]", "[explicit-any]", "[type-arg]", '[misc]'):
        assert code in result.stdout, result.stdout
