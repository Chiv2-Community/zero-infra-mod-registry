# Tests

```sh
uv sync --all-groups
uv run pytest
uv run mypy .
```

Use `uv run pytest --cov` for coverage. Set `REGISTRY_DOCKER_TEST_IMAGE` to an
existing registry image to enable Docker ownership tests. The remaining suite
runs without Docker.

## Validation coverage

`test_registry_reference.py` validates a pinned C2ModRegistry snapshot through the
CLI, then round-trips every package through the generated models and schemas.
The archive in `fixtures/` is downloaded unchanged from the live repository;
its full commit, source URL, and SHA-256 are recorded in that test. It contains
19 pak packages / 41 releases and one DLL package / four releases.

The snapshot is checked in so normal tests need neither GitHub credentials nor
network access. To refresh it, choose an explicit upstream commit, download
`https://codeload.github.com/Chiv2-Community/C2ModRegistry/tar.gz/<commit>`, and
update the test's pin, checksum, and expected counts. Do not rewrite its records
to make validation pass.

Trust `jsonschema` for individual field constraints. Focus other tests on our
behavior: compatibility normalization, dependency resolution, error context,
CLI failure propagation, download integrity, registration, and packaging.
Do not add field-by-field schema acceptance/rejection matrices.
