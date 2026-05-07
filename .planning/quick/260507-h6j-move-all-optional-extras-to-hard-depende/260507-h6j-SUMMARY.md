---
quick_id: 260507-h6j
status: complete
date: 2026-05-07
---

# Quick Task 260507-h6j — Summary

## What shipped

Flattened all `[project.optional-dependencies]` into `[project.dependencies]`. All database drivers (pyodbc, azure-identity, databricks-sqlalchemy, databricks-sql-connector, jupyter, notebook) are now hard deps. Deleted the `[project.optional-dependencies]` table. Dropped `"dbmcp[all]"` from `[dependency-groups].dev` since it no longer exists.

Updated install-hint strings in `src/db/dialects/{mssql,databricks}.py` and `src/mcp_server/_errors.py` from `pip install dbmcp[<extra>]` to `Reinstall dbmcp to pull it in.` — the extras syntax no longer resolves.

## Files changed

- `pyproject.toml` — deps flattened, extras table removed, dev group slimmed
- `src/db/dialects/mssql.py` — ImportError message updated
- `src/db/dialects/databricks.py` — ImportError message updated
- `src/mcp_server/_errors.py` — docstring example updated
- `tests/unit/test_pyproject_extras.py` — rewritten to assert hard-dep contract (no optional-dependencies)
- `tests/unit/test_optional_deps.py` — `ImportError` match pattern updated
- `tests/unit/test_databricks_dialect.py` — `ImportError` match pattern updated
- `tests/mcp_server/test_import_error_messaging.py` — fixture strings refreshed

## Verification

- `uv sync --group dev` → resolved 155 packages, no errors
- `uv run pytest -m "not integration and not slow" -q` → **953 passed, 78 skipped, 9 deselected**
- `uv run ruff check src/` → clean (CI-scope)
- `uv run python scripts/check_complexity.py` → passed (max=15)
- `uv build` → wheel + sdist built
- Wheel `METADATA` inspected: 10 `Requires-Dist`, zero `Provides-Extra` ✓

## Out of scope

- Lazy-import defensive guards in dialect modules are left in place (harmless dead code now; separate refactor if removing).
- Historical `.planning/milestones/` and `.planning/research/` artifacts still reference the old extras — those are frozen docs.
