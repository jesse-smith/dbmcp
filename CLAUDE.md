# dbmcp Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-19

## Active Technologies
- Python 3.11+ (matching main project) + Jupyter/IPython (notebook environment), existing DBMCP dependencies (mcp[cli], sqlalchemy, pyodbc) (002-example-notebooks)
- File-based (.ipynb files), test database schema (SQL scripts) (002-example-notebooks)
- Python 3.11+ + SQLAlchemy (existing), re module (stdlib) (003-allow-cte-queries)
- N/A (in-memory query processing only) (003-allow-cte-queries)

- Python 3.11+ + FastMCP (MCP SDK), pyodbc (SQL Server driver), SQLAlchemy (connection pooling + metadata introspection) (001-db-schema-explorer)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+: Follow standard conventions

## Recent Changes
- 003-allow-cte-queries: Added Python 3.11+ + SQLAlchemy (existing), re module (stdlib)
- 002-example-notebooks: Added Python 3.11+ (matching main project) + Jupyter/IPython (notebook environment), existing DBMCP dependencies (mcp[cli], sqlalchemy, pyodbc)

- 001-db-schema-explorer: Added Python 3.11+ + FastMCP (MCP SDK), pyodbc (SQL Server driver), SQLAlchemy (connection pooling + metadata introspection)

<!-- MANUAL ADDITIONS START -->

## Feature Completion Workflow

When a feature branch is merged to main:

1. **Hookify reminder**: A warning will appear when you run `git merge ###-*` commands
2. **Run `/speckit.complete`**: This skill updates status tracking:
   - Adds completion headers to spec.md, plan.md, tasks.md
   - Updates the central `specs/STATUS.md` registry
3. **Commit the status updates**

See `specs/STATUS.md` for the current feature registry.

## Companion Artifacts

When implementing phased features that need companion artifacts (e.g., example notebooks for each phase):
- Add companion artifact tasks to the **same feature's tasks.md** under each phase
- Do NOT create a separate parallel feature branch for companion work
- This keeps implementation and documentation synchronized

<!-- MANUAL ADDITIONS END -->
