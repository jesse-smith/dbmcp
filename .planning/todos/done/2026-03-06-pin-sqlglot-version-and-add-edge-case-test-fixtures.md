---
created: 2026-03-06T18:46:49.542Z
title: Pin sqlglot version and add edge case test fixtures
area: database
files:
  - src/db/validation.py:93-99
  - src/db/query.py:336-341
  - pyproject.toml
---

## Problem

sqlglot is the backbone of SQL query validation (`validation.py`) and query safety checks (`query.py`). Two risks:

1. **Parsing behavior changes**: Future sqlglot releases may change how malformed SQL is handled, potentially shifting parse failures from "blocked" to "allowed" or vice versa
2. **New SQL Server syntax**: New T-SQL features may break parsing assumptions

The current mitigation (ParseError → `is_safe=False`) is a safe default, but there's no test fixture suite specifically covering known edge cases, and the version isn't pinned to a specific minor version.

## Solution

1. **Pin sqlglot** to a specific minor version in `pyproject.toml` (e.g., `sqlglot>=X.Y,<X.Z`) rather than allowing unconstrained upgrades
2. **Create edge case test fixtures** covering: malformed SQL, SQL injection attempts, T-SQL-specific syntax (CTEs, MERGE, CROSS APPLY), Unicode identifiers, nested subqueries, and comment-based obfuscation
3. **Add telemetry** for parse failures to detect patterns (log unparseable SQL signatures)
4. **Monitor sqlglot changelog** on upgrades — run the edge case fixture suite before accepting new versions
