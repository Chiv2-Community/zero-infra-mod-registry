# Running Tests

If you're having trouble running the tests directly, try installing the package in development mode first:

```bash
poetry install -e .
```

Then run the tests:

```bash
poetry run pytest
```

For code coverage:

```bash
poetry run pytest --cov
```

## Troubleshooting

If you still have import issues, you can manually add the `src` directory to your Python path:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
poetry run pytest
```
