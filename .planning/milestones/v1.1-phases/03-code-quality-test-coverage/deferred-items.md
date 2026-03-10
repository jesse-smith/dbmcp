# Phase 03 Deferred Items

## Pre-existing Issues (Out of Scope)

1. **pyright: sqlglot.errors attribute access** - `src/db/query.py:337` reports `"errors" is not a known attribute of module "sqlglot"` (reportAttributeAccessIssue). This is a sqlglot type stub issue, not a code bug. Pre-existed before any Phase 03 changes.

2. **ruff: unused SQLAlchemyError import in connection.py** - `src/db/connection.py:16` has unused `SQLAlchemyError` import. Introduced by commit `2bc16d5` (03-02 plan). Not caused by 03-01 changes.
