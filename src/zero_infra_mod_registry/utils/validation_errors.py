"""Add source and field context without changing validation rules."""
from collections.abc import Iterator
from contextlib import contextmanager

from mod_registry_core.json_types import JsonObject


@contextmanager
def validation_context(source: str) -> Iterator[None]:
    try:
        yield
    except (ValueError, KeyError) as error:
        raise ValueError(f"{source}: {error}") from error


def require_fields(data: JsonObject, required: set[str], optional: set[str], source: str) -> None:
    problems: list[str] = []
    missing = required - data.keys()
    unexpected = data.keys() - required - optional
    if missing:
        problems.append(f"missing required fields: {', '.join(sorted(missing))}")
    if unexpected:
        problems.append(f"unexpected fields: {', '.join(sorted(unexpected))}")
    if problems:
        raise ValueError(f"{source}: {'; '.join(problems)}")
