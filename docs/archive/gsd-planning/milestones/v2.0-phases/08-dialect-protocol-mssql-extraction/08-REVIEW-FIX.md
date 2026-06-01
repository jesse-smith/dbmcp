---
phase: 08-dialect-protocol-mssql-extraction
fixed_at: 2026-04-14T14:45:00Z
review_path: .planning/phases/08-dialect-protocol-mssql-extraction/08-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 08: Code Review Fix Report

**Fixed at:** 2026-04-14T14:45:00Z
**Source review:** .planning/phases/08-dialect-protocol-mssql-extraction/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: SQL Injection via Bracket Quoting -- No Escaping of Closing Brackets

**Files modified:** `src/db/dialects/mssql.py`
**Commit:** 70dce1a
**Applied fix:** Added `.replace(']', ']]')` inside `quote_identifier` so that closing brackets within identifier values are properly escaped before wrapping in `[...]`. This prevents SQL injection when column names contain literal `]` characters.

### WR-01: Duplicated _classify_db_error Function

**Files modified:** `src/db/dialects/mssql.py`
**Commit:** ae345bd
**Applied fix:** Removed the duplicated `_classify_db_error` function and its unused `SQLAlchemyError` import from `src/db/dialects/mssql.py`. The canonical copy remains in `src/db/connection.py` where all existing consumers import from. No code in `mssql.py` or any other module imported the duplicate.

### WR-02: MetadataService and QueryService Silently Auto-Infer Dialect Without Registry

**Files modified:** `src/db/metadata.py`, `src/db/query.py`
**Commit:** e58d582
**Applied fix:** Replaced hardcoded `MssqlDialect()` instantiation with registry-based lookup via `get_dialect()`. Both `MetadataService.__init__` and `QueryService.__init__` now use `get_dialect(dialect_name)` with a `ValueError` fallback to `None`, ensuring custom dialect registrations are honored.

### WR-03: Type Annotation Shadowing in MetadataService.__init__

**Files modified:** `src/db/metadata.py`, `src/db/query.py`
**Commit:** e58d582
**Applied fix:** Addressed as part of the WR-02 fix. The `self._dialect` type annotation is now declared once before the conditional block in both services, eliminating the re-annotation inside the `elif` branch.

---

_Fixed: 2026-04-14T14:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
