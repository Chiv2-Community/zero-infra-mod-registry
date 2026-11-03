# Python workspace

The root project is the registry. Gateway, core, generated models, and code generation are uv workspace
members under `packages/`. Each builds its own wheel and source distribution. Both
applications depend on core; neither imports the other. Registry and core depend
on the independent generated-models package.

| Package | Sources | Purpose |
|---|---|---|
| `zero-infra-mod-registry` | `src/zero_infra_mod_registry/` | Registry CLI and metadata validation |
| `automated-registry-gateway` | `packages/automated-registry-gateway/src/automated_registry_gateway/` | Optional OIDC HTTP service |
| `mod-registry-core` | `packages/mod-registry-core/src/mod_registry_core/` | Shared typed JSON utilities |
| `generated-models` | `packages/generated-models/src/generated_models/` | Generated types, validation, loading, and serialization |
| `code-gen` | `packages/code-gen/src/code_gen/` | Development-only model generator (`python -m code_gen`) |

The root `pyproject.toml` defines the workspace and dev tools. Each member has its
own `pyproject.toml`. `uv.lock` covers all packages. Gateway is a dev dependency
of the root project so the full test suite is available after syncing.

```sh
uv sync --all-groups
uv build --all-packages
uv run mypy .
uv run pytest .
```

Run a single application without dev dependencies:

```sh
uv run --package zero-infra-mod-registry --no-dev zero-infra-mod-registry --help
uv run --package automated-registry-gateway --no-dev automated-registry-gateway --help
```

Registry Docker builds install the registry and core wheels. Gateway Docker builds
use `uv sync --package automated-registry-gateway --no-dev --no-editable --frozen`.
Neither runtime includes the other application. Packaging and Docker tests enforce
these boundaries.
