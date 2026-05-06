# Suggested Commands for dbmcp

## Critical Rule
**Always use `uv run`** for Python and Python-based tools. Never use bare `python`, `python3`, or `.venv/bin/python`.

## Testing
```bash
uv run pytest tests/                          # full suite
uv run pytest tests/unit/                     # unit tests only
uv run pytest -m "not integration"            # skip integration tests
uv run pytest -m "not slow"                   # skip slow tests
uv run pytest --cov=src --cov-report=term     # with coverage (fail_under=85)
uv run pytest tests/path/to/test_file.py::test_name   # single test
```

## Pytest markers available
- `integration`, `performance`, `slow`, `dialects(*names)` (e.g. `dialects('mssql')`)

## Linting / Formatting / Typing
```bash
uv run ruff check src/ tests/                 # lint
uv run ruff check --fix src/ tests/           # auto-fix
uv run ruff format src/ tests/                # format
uv run pyright                                # type check
uv run complexipy src/                        # complexity check
```

## Ruff config highlights
- line-length 120, target py311
- selected rules: E, W, F, I (isort), B, C4, UP
- ignored: E501, B008
- isort known-first-party: `src`

## Running the server
```bash
uv run dbmcp                                   # start MCP server (stdio)
```

## Dependency management
```bash
uv sync                                       # install/sync all deps
uv sync --all-extras                          # include mssql/databricks/examples
uv add <pkg>                                  # add runtime dep
uv add --dev <pkg>                            # add dev dep
```

## Darwin-specific system commands
- Standard BSD utilities (macOS). `grep`, `find`, `ls`, `sed` are BSD variants — prefer `rg` (ripgrep) if available for searching.
- `brew` for system packages (e.g., msodbcsql18)

## Git workflow
- Feature branches named like `###-feature-slug` or `gsd/...`
- Currently on `gsd/v2.0-multi-dialect-support`
- After merging feature to main: run `/speckit.complete` to update `specs/STATUS.md`
