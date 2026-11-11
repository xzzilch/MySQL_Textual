# Contributing

## Development setup

Use Python 3.12 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## Checks

Before opening a pull request, run:

```sh
python -m ruff check src tests packaging
python -m pytest -q
python -m compileall -q src tests packaging
```

The CI workflow runs lint and tests on Linux and Windows. Packaging is built separately on native operating-system runners because PyInstaller does not cross-compile.

## Scope and safety

- Keep presentation, MySQL access, and async execution in their existing layers.
- Never commit database credentials, connection dumps, or local build output.
- Include regression tests for error handling, query/resource cleanup, and async result ordering.
- Keep SQL identifiers escaped and metadata values parameterized.
