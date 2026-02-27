# dbmcp Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-19

## Active Technologies
- Python 3.11+ (matching main project) + Jupyter/IPython (notebook environment), existing DBMCP dependencies (mcp[cli], sqlalchemy, pyodbc) (002-example-notebooks)
- File-based (.ipynb files), test database schema (SQL scripts) (002-example-notebooks)
- Python 3.11+ + SQLAlchemy (existing), re module (stdlib) (003-allow-cte-queries)
- N/A (in-memory query processing only) (003-allow-cte-queries)
- Python 3.11+ (existing) + SQLAlchemy >=2.0.0, pyodbc >=5.0.0, azure-identity >=1.14.0 (new), mcp[cli] >=1.0.0 (existing) (004-azure-ad-integrated-auth)
- N/A (in-memory connection management only) (004-azure-ad-integrated-auth)
- Python 3.11+ (existing) + sqlglot (new), SQLAlchemy >=2.0.0 (existing), pyodbc >=5.0.0 (existing), mcp[cli] >=1.0.0 (existing) (005-denylist-query-validation)
- N/A (in-memory query validation only) (005-denylist-query-validation)

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
- 005-denylist-query-validation: Added Python 3.11+ (existing) + sqlglot (new), SQLAlchemy >=2.0.0 (existing), pyodbc >=5.0.0 (existing), mcp[cli] >=1.0.0 (existing)
- 004-azure-ad-integrated-auth: Added Python 3.11+ (existing) + SQLAlchemy >=2.0.0, pyodbc >=5.0.0, azure-identity >=1.14.0 (new), mcp[cli] >=1.0.0 (existing)
- 003-allow-cte-queries: Added Python 3.11+ + SQLAlchemy (existing), re module (stdlib)


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
