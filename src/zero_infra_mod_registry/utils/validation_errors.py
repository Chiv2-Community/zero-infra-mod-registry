"""Add source and field context without changing validation rules."""
from collections.abc import Iterator
from contextlib import contextmanager

@contextmanager
def validation_context(source: str) -> Iterator[None]:
    try:
        yield
    except (ValueError, KeyError) as error:
        raise ValueError(f"{source}: {error}") from error
