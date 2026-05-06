---
phase: 09-config-discrimination-validation-dialect
reviewed: 2026-04-14T12:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/config.py
  - src/db/dialects/mssql.py
  - src/db/dialects/protocol.py
  - src/db/query.py
  - src/db/validation.py
  - tests/compliance/test_nfr_compliance.py
  - tests/unit/test_config.py
  - tests/unit/test_dialect_protocol.py
  - tests/unit/test_query.py
  - tests/unit/test_validation.py
  - tests/unit/test_validation_edge_cases.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-04-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

The phase 9 code introduces multi-dialect config discrimination (MSSQL, Databricks, Generic), a DialectStrategy protocol, and dialect-aware query validation. The architecture is clean: frozen dataclasses for config, structural subtyping via Protocol, and dialect dispatch via a parser map. The validation module is well-designed with comprehensive denial categories and obfuscation resistance.

No critical security issues found. Two warnings relate to a docstring/count mismatch that could confuse maintainers and an unused fixture parameter pattern in tests. Three info items cover minor code quality points.

## Warnings

### WR-01: Docstring claims 22 safe procedures but set contains 21

**File:** `src/db/dialects/mssql.py:55`
**Issue:** The docstring on the `safe_procedures` property says "22 known-safe SQL Server system stored procedures" but the frozenset contains exactly 21 entries. The test at `tests/unit/test_validation.py:364` correctly asserts `len(procs) == 21`. This mismatch could mislead a maintainer into thinking a procedure was accidentally dropped, or cause them to add a 22nd entry they shouldn't.
**Fix:** Update the docstring to match reality:
```python
@property
def safe_procedures(self) -> frozenset[str]:
    """21 known-safe SQL Server system stored procedures."""
```

### WR-02: NFR-004 tests accept unused `mock_engine` fixture

**File:** `tests/compliance/test_nfr_compliance.py:187-228`
**Issue:** Every test method in `TestNFR004ReadOnlyEnforcement` declares `mock_engine` as a parameter but never uses it. The tests call `validate_query()` directly (a pure function with no engine dependency). This is misleading -- it suggests the engine is needed for validation, which is false. It also means if the fixture setup ever becomes expensive or breaks, these tests fail for the wrong reason.
**Fix:** Remove the `mock_engine` parameter from all test methods in `TestNFR004ReadOnlyEnforcement`:
```python
def test_select_allowed(self):
    """NFR-004: SELECT queries must be allowed."""
    result = validate_query("SELECT * FROM users", dialect="tsql")
    assert result.is_safe is True
```

## Info

### IN-01: f-string used in logger.error and logger.warning calls

**File:** `src/db/query.py:145-146,154`
**Issue:** Several logging calls use f-strings instead of %-style formatting. This evaluates the string even when the log level is disabled. Examples at lines 145-146 (`logger.warning(f"TABLESAMPLE returned...")`) and line 154 (`logger.error(f"Error sampling...")`). Line 159 in `mssql.py` has the same pattern.
**Fix:** Use lazy %-style formatting:
```python
logger.warning(
    "TABLESAMPLE returned 0 rows for %s.%s with sample_size=%d; falling back to TOP",
    schema_name, table_name, sample_size,
)
```

### IN-02: Unused `mock_engine` fixture in test_validation.py test classes

**File:** `tests/unit/test_validation.py:364` (and `tests/unit/test_query.py` in `TestCTEQueryParsing`, `TestReadOnlyEnforcement`)
**Issue:** Same pattern as WR-02 -- several test methods in `test_query.py` (`test_cte_write_blocked_by_default`, `test_cte_write_allowed_with_flag`, `test_existing_write_controls_unchanged`, `test_cte_select_allowed`, and all of `TestReadOnlyEnforcement`) accept `mock_engine` but only call `validate_query()`. Less impactful than the compliance tests but still misleading.
**Fix:** Remove unused `mock_engine` parameter from tests that only call `validate_query()`.

### IN-03: `hashlib.sha256` used for non-security sample_id generation

**File:** `src/db/query.py:160`
**Issue:** `sample_id` is generated via `hashlib.sha256(f"{table_id}_{timestamp}")[:12]`. This is not a security concern (sample IDs are informational), but the timestamp-based input makes the hash non-deterministic. If reproducibility were ever desired, this would be an obstacle. Current usage is fine -- just noting for awareness.
**Fix:** No action needed. If reproducibility becomes a requirement, switch to a deterministic input or use `uuid.uuid4().hex[:12]` to make the intent (random ID) explicit.

---

_Reviewed: 2026-04-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
