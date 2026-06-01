---
phase: 09-config-discrimination-validation-dialect
verified: 2026-04-14T20:30:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 9: Config Discrimination & Validation Dialect Verification Report

**Phase Goal:** Users can configure non-MSSQL connections via TOML and execute validated queries against any supported dialect
**Verified:** 2026-04-14T20:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | TOML config with dialect='mssql' produces MssqlConnectionConfig instance | ✓ VERIFIED | `_parse_mssql_connection()` in src/config.py lines 207-224, test coverage in tests/unit/test_config.py |
| 2 | TOML config with dialect='databricks' produces DatabricksConnectionConfig instance | ✓ VERIFIED | `_parse_databricks_connection()` in src/config.py lines 227-237, test coverage exists |
| 3 | TOML config with dialect='generic' produces GenericConnectionConfig instance | ✓ VERIFIED | `_parse_generic_connection()` in src/config.py lines 240-246, test coverage exists |
| 4 | TOML config missing dialect field raises ValueError with actionable message | ✓ VERIFIED | src/config.py lines 277-281: raises ValueError with "missing required 'dialect' field" and connection name |
| 5 | TOML config with unknown dialect value raises ValueError listing supported dialects | ✓ VERIFIED | src/config.py lines 282-287: raises ValueError listing supported dialects from `_DIALECT_PARSERS.keys()` |
| 6 | Unrecognized fields in a connection config produce a warning log and are silently ignored | ✓ VERIFIED | `_warn_unknown_fields()` in src/config.py lines 190-204 logs warnings for unknown fields |
| 7 | Existing AppConfig.connections type works with the new union type | ✓ VERIFIED | AppConfig.connections type annotation is `dict[str, ConnectionConfig]` where ConnectionConfig is TypeAlias union (lines 91-93) |
| 8 | validate_query requires an explicit dialect parameter with no default | ✓ VERIFIED | src/db/validation.py lines 45-51: `dialect: str` is keyword-only after `*`, no default value |
| 9 | validate_query passes the dialect parameter to sqlglot.parse() | ✓ VERIFIED | src/db/validation.py line 74: `sqlglot.parse(sql, dialect=dialect)` |
| 10 | validate_query accepts a safe_procedures frozenset parameter | ✓ VERIFIED | src/db/validation.py line 49: `safe_procedures: frozenset[str] = frozenset()` |
| 11 | MssqlDialect.safe_procedures returns the 21 sp_ frozenset | ✓ VERIFIED | src/db/dialects/mssql.py lines 54-82: returns frozenset with 21 procedures including sp_help |
| 12 | Denylist validation (INSERT/UPDATE/DELETE/CREATE/DROP) produces identical results for tsql and databricks dialects | ✓ VERIFIED | tests/unit/test_validation.py lines 337-343: parameterized test verifies identical denial categories |
| 13 | EXEC sp_help with dialect=tsql and MSSQL safe_procedures is allowed | ✓ VERIFIED | Test coverage exists, logic in src/db/validation.py lines 146-169 |
| 14 | EXEC sp_help with dialect=databricks produces PARSE_FAILURE (not STORED_PROCEDURE) | ✓ VERIFIED | tests/unit/test_validation.py lines 348-352: explicit test case |
| 15 | Production caller in QueryService threads dialect and safe_procedures to validate_query | ✓ VERIFIED | src/db/query.py lines 539-548: threads `dialect=dialect_str` and `safe_procedures=safe_procs` |
| 16 | All test calls pass with dialect parameter added | ✓ VERIFIED | 705 tests passed, 30+ validate_query calls in tests/unit/test_validation.py all have `dialect=` |

**Score:** 16/16 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | Per-dialect frozen dataclasses and dispatch-based _parse_connections | ✓ VERIFIED | MssqlConnectionConfig (lines 55-68), DatabricksConnectionConfig (lines 71-80), GenericConnectionConfig (lines 83-88), _DIALECT_PARSERS dict (lines 249-253), _parse_connections dispatch (lines 256-289) |
| `tests/unit/test_config.py` | Config discrimination tests | ✓ VERIFIED | 51 tests pass including TestDialectConfigDataclasses, TestDialectDispatch, TestBackwardCompat |
| `src/db/dialects/protocol.py` | safe_procedures property on DialectStrategy | ✓ VERIFIED | Lines 74-80: `def safe_procedures(self) -> frozenset[str]` with docstring |
| `src/db/dialects/mssql.py` | MssqlDialect.safe_procedures returning sp_ frozenset | ✓ VERIFIED | Lines 54-82: property returns frozenset with 21 MSSQL system procedures |
| `src/db/validation.py` | Dialect-aware validate_query with explicit parameters | ✓ VERIFIED | Lines 45-51: signature with keyword-only `dialect: str`, `safe_procedures: frozenset[str]` |
| `src/db/query.py` | Production caller threading dialect to validate_query | ✓ VERIFIED | Lines 539-548: composes dialect_str and safe_procs from self._dialect, threads to validate_query |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| src/config.py | _DIALECT_PARSERS dict | dict-based dispatch in _parse_connections | ✓ WIRED | Line 282: `parser = _DIALECT_PARSERS.get(dialect)` |
| src/db/query.py | src/db/validation.py | validate_query call with dialect and safe_procedures | ✓ WIRED | Lines 543-548: calls validate_query with dialect= and safe_procedures= keywords |
| src/db/validation.py | sqlglot.parse | dialect parameter passthrough | ✓ WIRED | Line 74: `sqlglot.parse(sql, dialect=dialect)` |
| src/db/query.py | src/db/dialects/protocol.py | self._dialect.safe_procedures | ✓ WIRED | Lines 540-542: accesses `self._dialect.safe_procedures` |

### Data-Flow Trace (Level 4)

Not applicable — config and validation modules are pure functions with no external data sources. All data flows from function parameters.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest tests/ -x -q` | 705 passed, 41 skipped | ✓ PASS |
| Config tests pass | `uv run pytest tests/unit/test_config.py -x -q` | 51 passed | ✓ PASS |
| Validation tests pass | `uv run pytest tests/unit/test_validation.py -x -q` | 90 passed | ✓ PASS |
| MssqlConnectionConfig exists | `grep -c "class MssqlConnectionConfig" src/config.py` | 1 | ✓ PASS |
| DatabricksConnectionConfig exists | `grep -c "class DatabricksConnectionConfig" src/config.py` | 1 | ✓ PASS |
| GenericConnectionConfig exists | `grep -c "class GenericConnectionConfig" src/config.py` | 1 | ✓ PASS |
| _DIALECT_PARSERS exists | `grep -c "_DIALECT_PARSERS" src/config.py` | 2 | ✓ PASS |
| dialect parameter in validate_query | `grep -c "dialect: str" src/db/validation.py` | 1 | ✓ PASS |
| safe_procedures in protocol | `grep -c "safe_procedures" src/db/dialects/protocol.py` | 3 | ✓ PASS |
| safe_procedures in MssqlDialect | `grep -c "safe_procedures" src/db/dialects/mssql.py` | 2 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CONF-01 | 09-01 | TOML config supports `dialect` discriminator field | ✓ SATISFIED* | *Implementation requires dialect explicitly (overrides "default to mssql" from original requirement per D-02 decision). Config parsing in src/config.py lines 256-289. |
| CONF-02 | 09-01 | Typed config models validate dialect-specific fields | ✓ SATISFIED | Three frozen dataclasses (MssqlConnectionConfig, DatabricksConnectionConfig, GenericConnectionConfig) with dialect-specific fields. Unknown field warnings in `_warn_unknown_fields()`. |
| VALID-01 | 09-02 | validate_query accepts dialect parameter and passes it to sqlglot.parse() | ✓ SATISFIED | src/db/validation.py line 48: `dialect: str` parameter, line 74: `sqlglot.parse(sql, dialect=dialect)` |
| VALID-02 | 09-02 | Safe procedure list is dialect-aware (MSSQL sp_ list; empty for Databricks/generic) | ✓ SATISFIED | Protocol property in src/db/dialects/protocol.py lines 74-80, MssqlDialect implementation returns 21 procedures, other dialects return empty frozenset |
| VALID-03 | 09-02 | Denylist validation (INSERT/UPDATE/DELETE/CREATE/DROP) works unchanged across all sqlglot dialects | ✓ SATISFIED | Cross-dialect test in tests/unit/test_validation.py lines 337-343 verifies identical denial categories for tsql and databricks |

**Note on CONF-01:** The ROADMAP success criteria states "omitting `dialect` defaults to 'mssql'" but the implementation requires dialect explicitly. This was an **intentional decision documented in Phase 9 Context (D-02)**: "The `dialect` field in TOML is always required for every connection. This overrides CONF-01's original 'default to mssql' spec — explicit over implicit." The Context document notes at line 98 that "CONF-01 requirement should be updated to reflect 'dialect always required' decision." The implementation is correct; the ROADMAP success criteria needs updating.

### Anti-Patterns Found

No anti-patterns found. Spot-checked modified files:
- src/config.py: No TODO/FIXME/placeholder comments, no empty implementations
- src/db/dialects/protocol.py: No TODO/FIXME/placeholder comments, no empty implementations
- src/db/dialects/mssql.py: No TODO/FIXME/placeholder comments, no empty implementations
- src/db/validation.py: Empty list returns (lines 143, 168, 234) are valid guard clauses in classification functions
- src/db/query.py: No new anti-patterns introduced

### Human Verification Required

None — all validation is automated and passed.

---

## Verification Summary

Phase 9 successfully implements config discrimination and dialect-aware validation:

1. **Config Discrimination (Plan 01):** Three per-dialect frozen dataclasses with dict-based dispatch in `_parse_connections()`. ConnectionConfig is now a TypeAlias union. Missing dialect raises clear ValueError. Unknown fields produce warning logs. 51 tests pass.

2. **Validation Dialect Awareness (Plan 02):** validate_query accepts required keyword-only `dialect` parameter (no default) and optional `safe_procedures` parameter. sqlglot.parse receives dialect parameter. SAFE_PROCEDURES moved from module constant to MssqlDialect.safe_procedures protocol property. All 44+ test call sites updated with explicit `dialect="tsql"`. Production caller threads dialect and merged safe_procedures. Cross-dialect tests verify identical denylist behavior. 90 validation tests pass.

3. **Requirements:** All 5 requirements (CONF-01*, CONF-02, VALID-01, VALID-02, VALID-03) satisfied. CONF-01 implementation intentionally deviates from original "default to mssql" spec per documented Phase 9 Context decision D-02 (explicit over implicit).

4. **Test Coverage:** Full test suite passes (705 passed, 41 skipped). Zero regressions.

5. **Wiring:** All key links verified. Config dispatch, validation threading, protocol usage all wired correctly.

**Deviation Note:** ROADMAP success criteria #1 states "omitting `dialect` defaults to 'mssql'" but implementation requires it explicitly. This is an **intentional, documented decision** from Phase 9 Context (D-02) prioritizing explicit over implicit. The Context document flags that ROADMAP should be updated. This is not a gap — it's a design refinement that should be reflected in the ROADMAP.

**Phase goal achieved.** Users can configure non-MSSQL connections via TOML with typed config models and execute validated queries against any supported dialect.

---

_Verified: 2026-04-14T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
