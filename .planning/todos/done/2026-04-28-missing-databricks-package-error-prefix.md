---
created: 2026-04-28T17:15:00.000Z
title: Missing-databricks-package error surfaces as "Unexpected error:" — reads like a bug, not an install hint
area: mcp-server
source: .planning/phases/11-databricksdialect/11-UAT.md (Test 6 gap)
files:
  - src/mcp_server/schema_tools.py:191-196
  - src/db/dialects/databricks.py (ImportError raise site)
---

## Problem

When `databricks-sqlalchemy` is not installed and a user calls
`connect_database(sqlalchemy_url="databricks://...")`, the dialect module raises
a clear `ImportError`:

> Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]

But `connect_database`'s generic exception handler wraps it:

> `Unexpected error: ImportError: Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]`

The "Unexpected error:" prefix makes the message read like an internal bug the
user should report, when it's actually an actionable install hint they should
follow. It also shifts emphasis away from the actionable part of the message.

Noted during Phase 11 UAT (Test 6) — non-blocking, test passed, but worth a
polish pass.

## Solution

Candidates:

1. In `connect_database` (src/mcp_server/schema_tools.py:191-196), special-case
   `ImportError` (and likely `ModuleNotFoundError`) to surface the message
   verbatim without the "Unexpected error:" prefix. Rationale: import errors
   at connect time are almost always missing optional extras, not internal bugs.
2. More general: catch `ImportError` earlier (e.g., in dialect resolution) and
   return a dedicated error path that doesn't go through the generic handler.
3. Do both — (2) for the structural fix, (1) as belt-and-suspenders.

Similar prefixes exist in `src/mcp_server/analysis_tools.py` (lines 143, 247,
403); audit those paths for the same ergonomic issue while we're in there.

## Acceptance

- `connect_database(sqlalchemy_url="databricks://...")` with databricks-sqlalchemy
  absent returns an error message that starts with the install hint, not with
  "Unexpected error:".
- A unit test pins the wording so future refactors don't regress it.
