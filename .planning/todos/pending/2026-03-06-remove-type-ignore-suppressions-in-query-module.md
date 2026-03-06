---
created: 2026-03-06T18:32:42.028Z
title: Remove type ignore suppressions in query module
area: database
files:
  - src/db/query.py:546-548
---

## Problem

Three `# type: ignore` suppressions in `src/db/query.py` lines 546-548 bypass static analysis. Runtime attributes are being set on the `Query` dataclass (`Query._columns`, `Query._rows`, `Query._total_rows_available`) that aren't declared in the class definition, hiding these modifications from type checkers.

This means changes to the Query dataclass or its consumers won't get caught by static analysis if they break assumptions about these hidden attributes.

## Solution

Either:
1. **Extend the Query dataclass** with optional fields for `_columns`, `_rows`, `_total_rows_available` (e.g., `field(default=None)`) so they're visible to type checkers
2. **Use a TypedDict** or separate result dataclass for query results instead of mutating the Query object

Option 1 is simpler; option 2 is cleaner separation of concerns.
