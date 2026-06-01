---
phase: 08-dialect-protocol-mssql-extraction
reviewed: 2026-04-14T14:32:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - src/db/azure_auth.py
  - src/db/connection.py
  - src/db/dialects/__init__.py
  - src/db/dialects/azure_auth.py
  - src/db/dialects/mssql.py
  - src/db/dialects/protocol.py
  - src/db/dialects/registry.py
  - src/db/metadata.py
  - src/db/query.py
  - tests/compliance/test_nfr_compliance.py
  - tests/unit/test_azure_auth.py
  - tests/unit/test_connection.py
  - tests/unit/test_dialect_protocol.py
  - tests/unit/test_dialect_registry.py
  - tests/unit/test_mssql_dialect.py
  - tests/unit/test_query_timeout.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-04-14T14:32:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This review covers the dialect protocol extraction in phase 08: introducing a `DialectStrategy` protocol, an `MssqlDialect` implementation, a dialect registry, and refactoring `ConnectionManager`, `MetadataService`, and `QueryService` to use the new abstractions. The protocol design is clean and the extraction is well-structured. Tests are thorough with good coverage of auth methods, token lifecycle, and error propagation.

Seven findings were identified: one critical SQL injection concern in `quote_identifier`, three warnings around code duplication and a potential bug, and three informational items.

## Critical Issues

### CR-01: SQL Injection via Bracket Quoting -- No Escaping of Closing Brackets

**File:** `src/db/dialects/mssql.py:106-107`
**Issue:** `quote_identifier` wraps the identifier in square brackets (`[{identifier}]`) but does not escape closing brackets within the identifier value. In SQL Server, a literal `]` inside a bracket-quoted identifier must be doubled (`]]`). An attacker-controlled identifier containing `]` can break out of the quoting, enabling SQL injection. This method is called from `QueryService._sanitize_identifier` and `_validate_identifier` to build SQL for `get_sample_data`, meaning user-supplied column names flow through this path.

The regex guard in `_sanitize_identifier` (`^[a-zA-Z0-9_\s]+$`) would block `]` in the regex-validated path, but the metadata-validated path (`_validate_identifier`) does not apply that regex -- it validates against known column names and then passes directly to `quote_identifier`. If a database column name itself contains a `]` (which is legal in SQL Server), the generated SQL becomes malformed or exploitable.

**Fix:**
```python
def quote_identifier(self, identifier: str) -> str:
    """Quote using SQL Server square brackets."""
    return f"[{identifier.replace(']', ']]')}]"
```

## Warnings

### WR-01: Duplicated _classify_db_error Function

**File:** `src/db/dialects/mssql.py:27-75` and `src/db/connection.py:57-105`
**Issue:** `_classify_db_error` is defined identically in both `src/db/connection.py` and `src/db/dialects/mssql.py`. This is a DRY violation -- the function in `connection.py` appears to be a leftover from before the extraction. If behavior diverges during maintenance, one copy will silently become stale. Tests in `test_connection.py` import from `src.db.connection`, so the `mssql.py` copy is currently untested directly.

**Fix:** Remove `_classify_db_error` from `src/db/connection.py` and import it from `src/db/dialects/mssql` instead. Alternatively, move it to a shared `src/db/errors.py` module if it should be dialect-agnostic. Update the test import accordingly.

### WR-02: MetadataService and QueryService Silently Auto-Infer Dialect Without Registry

**File:** `src/db/metadata.py:56-62` and `src/db/query.py:67-73`
**Issue:** Both `MetadataService.__init__` and `QueryService.__init__` contain identical fallback logic that instantiates `MssqlDialect()` directly when `dialect is None` and `engine.dialect.name == "mssql"`. This bypasses the dialect registry entirely, meaning a custom MSSQL dialect registered via `register_dialect("mssql", CustomMssqlDialect)` would be silently ignored. The registry pattern was introduced specifically to enable this kind of substitution.

**Fix:** Use the registry for auto-inference:
```python
if dialect is not None:
    self._dialect = dialect
else:
    from src.db.dialects.registry import get_dialect
    try:
        dialect_cls = get_dialect(self.dialect_name)
        self._dialect = dialect_cls()
    except ValueError:
        self._dialect = None
```

### WR-03: Type Annotation Shadowing in MetadataService.__init__

**File:** `src/db/metadata.py:60`
**Issue:** The line `self._dialect: DialectStrategy | None = MssqlDialect()` re-annotates `self._dialect` inside the `elif` branch after it was already set in the `if` branch (line 57). This is a mypy/pyright concern -- the re-annotation in a branch is legal but confusing and may produce type-checker warnings about variable redefinition. The same pattern appears in `src/db/query.py:71`.

**Fix:** Annotate `self._dialect` once before the conditional block:
```python
self._dialect: DialectStrategy | None
if dialect is not None:
    self._dialect = dialect
elif self.dialect_name == "mssql":
    from src.db.dialects.mssql import MssqlDialect
    self._dialect = MssqlDialect()
else:
    self._dialect = None
```

## Info

### IN-01: Backward-Compatibility Shim Has No Deprecation Warning

**File:** `src/db/azure_auth.py:1-9`
**Issue:** The shim re-exports `AzureTokenProvider` and `SQL_COPT_SS_ACCESS_TOKEN` from the new location but does not emit a `DeprecationWarning`. Consumers importing from the old path will silently continue working with no signal to migrate.

**Fix:** Add a module-level deprecation warning:
```python
import warnings
warnings.warn(
    "src.db.azure_auth is deprecated; import from src.db.dialects.azure_auth instead",
    DeprecationWarning,
    stacklevel=2,
)
```

### IN-02: Registry Allows Silent Overwrite Without Warning

**File:** `src/db/dialects/registry.py:13-15`
**Issue:** `register_dialect` silently overwrites an existing registration for the same name. While the test suite explicitly tests this behavior, a logging warning on overwrite would help catch accidental double-registration bugs in production.

**Fix:** Add a debug log when overwriting:
```python
def register_dialect(name: str, dialect_class: type[DialectStrategy]) -> None:
    if name in _REGISTRY:
        logger.debug(f"Overwriting dialect registration for '{name}'")
    _REGISTRY[name] = dialect_class
```

### IN-03: Unused mock_engine Fixture in NFR-004 Tests

**File:** `tests/compliance/test_nfr_compliance.py:183-186`
**Issue:** The `mock_engine` fixture in `TestNFR004ReadOnlyEnforcement` is injected into every test method but never used -- `validate_query` does not require an engine. This is dead code that adds confusion.

**Fix:** Remove the `mock_engine` fixture and its parameter from all test methods in that class.

---

_Reviewed: 2026-04-14T14:32:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
