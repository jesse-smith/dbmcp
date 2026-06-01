---
phase: 15-unified-identifier-resolver-cross-dialect
verified: 2026-05-28T23:45:00Z
reconciled: 2026-05-29T03:05:00Z
status: verified
score: 5/5 must-haves verified
overrides_applied: 0
gaps_resolved:
  - truth: "get_sample_data produces valid SQL for all dialect/schema combinations (SC3 + implicit SC4 correctness)"
    closed_by: ["260528-qcp", "src/db/query.py None-guard (else + Databricks elif branches)"]
    evidence: "tests/unit/test_query.py:1095 real-dialect schema_name=None regression test; live Databricks probe (get_sample_data 3-part dotted, catalog bmtct) returns rows with no corrupt 'None'.'table' SQL; 15-UAT.md Test 6 PASS; full suite 1069 passed / 78 skipped / 91% coverage."
    note: "Original gaps_found record (CR-01) preserved verbatim below under the historical body for audit trail."
gaps_historical:
  - truth: "get_sample_data produces valid SQL for all dialect/schema combinations (SC3 + implicit SC4 correctness)"
    status: failed
    reason: >
      query.py:133 else-branch passes schema_name=None to quote_identifier when
      generic dialect (default_schema=None) receives a bare table_name.
      GenericDialect.quote_identifier(None) returns '"None"', producing
      '"None"."orders"' — a query against a nonexistent schema literally named None.
      MssqlDialect.quote_identifier(None) raises AttributeError (uncaught).
      The Databricks elif branch (lines 127-131) has the same defect when
      resolved.catalog is set but resolved.schema is None (explicit catalog= +
      bare table_name without schema_name= on Databricks).
      Test coverage: the existing test_get_sample_data_none_schema_builds_unqualified_reference
      passes because it constructs QueryService(engine) with no dialect (_dialect=None),
      hitting the first if branch — not the broken else branch. No test covers the
      "non-None dialect + schema_name=None" path through the service layer.
    artifacts:
      - path: "src/db/query.py"
        issue: "Line 133: quote_identifier(schema_name) called unconditionally in else branch; no None-guard. Line 128-131: same issue in Databricks 3-part branch when schema_name is None."
      - path: "tests/unit/test_query.py"
        issue: "TestSampleDataSchemaDefault tests only cover _dialect=None path, not real dialect with schema_name=None."
    missing:
      - "Guard the else branch: when schema_name is None emit a bare quoted table name (no schema prefix). Fix the Databricks elif branch similarly."
      - "Add a QueryService-level test: GenericDialect() + schema_name=None produces an unqualified table reference, not '\"None\".\"table\"'."
---

# Phase 15: Unified Identifier Resolver — Verification Report

**Phase Goal:** Land one shared identifier resolver used by all namespace-aware tools. Dialect-aware depth (3/2/1), strict conflict detection between table_name and explicit params, dialect-aware default schema.
**Verified:** 2026-05-28T23:45:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All namespace-aware tools parse table_name per dialect depth through shared resolver | ✓ VERIFIED | resolve_identifier called in all 7 tool _sync_work bodies; depth validated via len(parts) against dialect.max_identifier_depth |
| 2 | Conflicts between table_name leading segments and explicit params produce named errors | ✓ VERIFIED | identifiers.py:113-122 raises ValueError with "Conflicting schema/catalog" message; wired in all 7 tools via resolve_identifier |
| 3 | get_sample_data and get_column_info have catalog param; 3-part dotted Databricks references work | ✗ FAILED | Catalog param exists and the 3-part dotted path works. But query.py else-branch passes None to quote_identifier when generic dialect has no schema, producing '"None"."table"'. MssqlDialect raises AttributeError on None. See CR-01. |
| 4 | No tool signature in src/mcp_server/ carries schema_name: str = "dbo" | ✓ VERIFIED | grep -rn 'schema_name: str = "dbo"' src/mcp_server/ → 0 matches confirmed |
| 5 | Full test suite green; 85% coverage floor maintained | ✓ VERIFIED | 1065 passed, 78 skipped; coverage 91% > 85% floor |

**Score:** 4/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/db/identifiers.py` | resolve_identifier + ResolvedIdentifier + _assert_catalog_allowed | ✓ VERIFIED | 129 lines, fully implemented with depth check (len(parts)), conflict detection, catalog gate |
| `src/db/dialects/protocol.py` | default_schema + max_identifier_depth on DialectStrategy | ✓ VERIFIED | Both properties declared with docstrings at lines 52-60 |
| `src/db/dialects/mssql.py` | default_schema="dbo", max_identifier_depth=2 | ✓ VERIFIED | Lines 63-70 return "dbo" and 2 |
| `src/db/dialects/databricks.py` | default_schema=None, max_identifier_depth=3 | ✓ VERIFIED | Lines 105-112 return None and 3 |
| `src/db/dialects/generic.py` | default_schema=None, max_identifier_depth=1 | ✓ VERIFIED | Lines 65-72 return None and 1 |
| `src/mcp_server/schema_tools.py` | list_tables + get_table_schema routed through resolver; list_schemas uses _assert_catalog_allowed | ✓ VERIFIED | resolve_identifier at lines 357+478; _assert_catalog_allowed at line 357 for list_tables |
| `src/mcp_server/query_tools.py` | get_sample_data routed through resolver with catalog param | ✓ WIRED (defect in downstream service) | resolve_identifier at line 98; catalog=resolved.catalog passed to QueryService. Defect is in QueryService.get_sample_data, not at the tool boundary. |
| `src/mcp_server/analysis_tools.py` | get_column_info + find_pk + find_fk routed through resolver | ✓ VERIFIED | resolve_identifier at lines 108, 251, 393 |
| `src/db/query.py` | get_sample_data builds valid SQL for all schema states | ✗ DEFECT | Line 133 else-branch: quote_identifier(schema_name) with schema_name=None produces invalid SQL for generic and Databricks dialects |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| All 7 tool _sync_work bodies | src.db.identifiers.resolve_identifier | import + call | ✓ WIRED | 4 calls in analysis_tools.py, 1 in query_tools.py, 1 in schema_tools.py (get_table_schema); list_tables uses _assert_catalog_allowed (no table_name to resolve) |
| resolve_identifier ValueError | tool error_message response | except ValueError | ✓ WIRED | All 7 tools catch ValueError and return status=error |
| dialect.max_identifier_depth | depth check in resolver | identifiers.py:99 | ✓ WIRED | len(parts) > dialect.max_identifier_depth → ValueError |
| dialect.default_schema | final_schema fallback in resolver | identifiers.py:125 | ✓ WIRED | final_schema = parsed_schema or schema_name or dialect.default_schema |
| resolved.catalog | query.py Databricks branch | query_tools.py:108 resolved.catalog → QueryService.get_sample_data catalog= | ✓ WIRED (with defect) | catalog is passed through. Defect is in QueryService.get_sample_data's handling of None schema_name in else branch. |
| resolved.catalog | analysis_tools.py get_column_info | MetadataService.table_exists(catalog=resolved.catalog) | ✓ WIRED | Lines 119-124 use resolved.catalog for cross-catalog existence check on Databricks |
| resolved.catalog | analysis_tools.py find_pk/find_fk | Not threaded to Inspector | ⚠ DOCUMENTED LIMITATION | Both tools accept and gate catalog but Inspector binds to connection's default catalog. Explicitly documented in plan decisions and tool comments. Not a SC3 requirement for these tools. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| query.py get_sample_data | full_table_name (else branch) | quote_identifier(schema_name) | ✗ Produces '"None"."table"' when schema_name=None | ✗ HOLLOW — wired but data disconnected for None schema |
| identifiers.py resolve_identifier | ResolvedIdentifier.schema | parsed_schema or schema_name or dialect.default_schema | ✓ Returns None for generic/bare table (by design) | ✓ FLOWING — resolver correct; downstream consumer (query.py) is the defect site |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| quote_identifier(None) on GenericDialect | `uv run python3 -c "from src.db.dialects.generic import GenericDialect; print(repr(GenericDialect().quote_identifier(None)))"` | `'"None"'` | ✗ FAIL — confirms CR-01: None schema produces a literal string "None" |
| quote_identifier(None) on MssqlDialect | `uv run python3 -c "from src.db.dialects.mssql import MssqlDialect; MssqlDialect().quote_identifier(None)"` | `AttributeError: 'NoneType' object has no attribute 'replace'` | ✗ FAIL — confirms CR-01: MSSQL crashes |
| resolve_identifier 3-part Databricks | `resolve_identifier("cat.sch.tbl", None, None, DatabricksDialect())` | `ResolvedIdentifier(catalog='cat', schema='sch', table='tbl')` | ✓ PASS |
| resolve_identifier explicit catalog + bare table on Databricks | `resolve_identifier("mytable", None, "mycat", DatabricksDialect())` | `ResolvedIdentifier(catalog='mycat', schema=None, table='mytable')` | ✓ PASS (resolver correct; downstream broken) |
| Dialect properties | `uv run pytest -k "default_schema or max_identifier_depth" -q` | 6 passed | ✓ PASS |
| Full test suite | `uv run pytest --tb=no -q` | 1065 passed, 78 skipped | ✓ PASS |
| Coverage | `uv run pytest --cov=src` | 91% > 85% floor | ✓ PASS |
| No dbo in tool signatures | `grep -rn 'schema_name: str = "dbo"' src/mcp_server/` | 0 matches | ✓ PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IDENT-03 | 15-01, 15-03, 15-06 | Shared resolver parses table_name per dialect depth; over-depth → clear error | ✓ SATISFIED | identifiers.py len(parts) depth check; max_identifier_depth on all 3 dialect impls; 53 resolver tests pass |
| IDENT-04 | 15-03, 15-04, 15-06 | Conflict between table_name leading segment and matching explicit param → named error | ✓ SATISFIED | identifiers.py:113-122 conflict detection; wired in all 7 tools; TestResolverConflictBoundary covers all 7 tools |
| IDENT-05 | 15-05 | get_sample_data accepts optional catalog on Databricks; MSSQL/generic → error | ✓ SATISFIED (with noted defect) | catalog param at query_tools.py:32; gate via resolve_identifier; TestCatalogGateBoundary covers MSSQL rejection. Defect (CR-01) is in None-schema SQL building, not the gate itself. |
| IDENT-06 | 15-05 | get_column_info accepts optional catalog on Databricks; same gate as IDENT-05 | ✓ SATISFIED | catalog param at analysis_tools.py:34; resolved.catalog threaded to MetadataService.table_exists for cross-catalog existence check |
| IDENT-07 | 15-01, 15-02, 15-06 | Each dialect advertises default_schema; no hardcoded schema='dbo' in tool signatures | ✓ SATISFIED (with noted residual) | default_schema on all 3 impls; 0 matches for 'schema_name: str = "dbo"' in src/mcp_server/. Residual: metadata.py:919 fk.get("referred_schema", "dbo") — hardcoded dbo in FK serialization body (not a signature, not in scope of IDENT-07 literal text, documented as WR-05 in review) |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/db/query.py | 133 | `quote_identifier(schema_name)` with no None guard in else branch | ✗ Blocker | Produces `"None"."table"` for generic dialect; AttributeError for MSSQL when schema_name is None (post-resolver where default_schema=None) |
| src/db/query.py | 128-131 | Same unguarded quote_identifier(schema_name) in Databricks elif branch | ✗ Blocker | Produces `` `None`.`table` `` when catalog is provided but schema_name resolves to None |
| src/db/metadata.py | 919 | `fk.get("referred_schema", "dbo")` — hardcoded "dbo" fallback | ⚠ Warning | Stamps MSSQL-specific "dbo" as target_schema for FK relationships on Databricks/generic connections; misleading output. WR-05 in code review. |
| tests/unit/test_async_tools.py | 281-282 | E402 module-level import not at top | ℹ Info | Pre-existing; acknowledged in deferred-items.md; ruff passes because not flagged at this severity |

---

### Code Review Findings (CR-01 and CR-02)

#### CR-01: query.py else-branch None-schema defect — BLOCKER

**Assessment: Real defect, not SC3's primary scenario but touches SC3 surface.**

The CR-01 defect exists and was confirmed by direct testing:
- `GenericDialect().quote_identifier(None)` → `'"None"'` — produces `"None"."orders"` in SQL
- `MssqlDialect().quote_identifier(None)` → `AttributeError`

**Where it bites:**
1. Any non-MSSQL connection (generic: SQLite, PostgreSQL, etc.) calling `get_sample_data` with a bare table name. The resolver returns `schema=None` (generic `default_schema=None`), then `query.py:133` builds invalid SQL.
2. Databricks `elif` branch (lines 127-131): if `catalog` is set but `schema_name` resolves to `None` (user passes `catalog=` explicitly without `schema_name=`), produces `` `None`.`table` ``.

**Impact on SC3:** SC3 reads "3-part Databricks references work end-to-end." A 3-part dotted name always produces a non-None schema (parts[-2]) so the pure 3-part case is unaffected. The defect does not break SC3's 3-part dotted path. However, the defect is a regression introduced by this phase (removing `schema_name="dbo"` default exposed the unguarded None path) and breaks `get_sample_data` for generic dialect users — a meaningful correctness gap.

**Note:** The pre-existing test `test_get_sample_data_none_schema_builds_unqualified_reference` passes because it tests `QueryService(engine)` with `_dialect=None` (the SQLite/test path). It does not test a real dialect instance with `schema_name=None`.

**Verdict:** BLOCKER — the defect is a phase-introduced regression in a primary deliverable (`get_sample_data`) that produces corrupt SQL silently on generic connections.

#### CR-02: find_pk/fk discard resolved.catalog — WITHIN DOCUMENTED POSTURE

**Assessment: Not a goal failure; deliberate KISS posture, explicitly documented.**

The PLAN 06 `decisions:` section states:
> "find_pk/fk use the Inspector path bound to the connection's default catalog (KISS, same as get_column_info); resolver GATES catalog rather than threading it cross-catalog through the Inspector"

The tool code confirms this with inline comments. The gate ensures that a `catalog` value on MSSQL/generic returns an error. On Databricks, passing a catalog that differs from the connection's default catalog is accepted by the gate but is not routed to the Inspector — users get results from the default catalog. This is silent mis-targeting for the cross-catalog case.

SC3 explicitly names only `get_sample_data` and `get_column_info` for the catalog parameter requirement. D-14 added find_pk/fk to the resolver for IDENT-03/04/07 purposes (depth, conflict, dbo-sweep), not for full cross-catalog support. The behavior gap documented by CR-02 is real but is within D-14's acknowledged scope boundary. It warrants a WARNING, not a BLOCKER.

---

### Gaps Summary

One blocker gap prevents marking this phase as passed.

**Root cause:** The removal of `schema_name: str = "dbo"` defaults from tool signatures (SC4/IDENT-07) correctly propagates `None` through to `QueryService.get_sample_data`. But `QueryService.get_sample_data`'s `else` branch (line 133) was not updated to handle `None` schema — it calls `quote_identifier(schema_name)` unconditionally, producing invalid SQL when no schema is available. The fix is a one-line guard: when `schema_name` is `None`, emit a bare quoted table name instead of `"None"."table"`. The Databricks `elif` branch needs the same guard.

This is a phase-introduced regression. The test suite passes because the existing coverage tests the `_dialect=None` code path, not a real dialect with `schema_name=None`.

---

### Human Verification Required

None. All gaps are programmatically verifiable.

---

_Verified: 2026-05-28T23:45:00Z_
_Verifier: Claude (gsd-verifier)_

---

## Reconciliation 2026-05-29 — gap closed, status → verified

The single BLOCKER gap (CR-01: `query.py` None-schema corrupt SQL) recorded above
was closed after the initial verification and is now confirmed closed through four
independent lines of evidence:

| Evidence | Result |
|----------|--------|
| Code fix | `src/db/query.py` else-branch + Databricks elif-branch now guard `if schema_name:`; bare quoted table emitted when schema is None (quick task `260528-qcp`) |
| Regression test | `tests/unit/test_query.py:1095` — real-dialect (`GenericDialect`/`MssqlDialect`) `schema_name=None` produces an unqualified reference, not `"None"."table"` |
| Live UAT | `15-UAT.md` Test 6 — Databricks 3-part `bmtct.playground.caboodle_tests` returns 3 live rows, no `USE CATALOG`, no corrupt SQL (PASS) |
| Full suite | 1069 passed, 78 skipped, 91% coverage (> 85% floor) |

All 5 observable truths now verified (Truth 3 flipped ✗ → ✓). The CR-02 find_pk/fk
cross-catalog limitation remains a documented WARNING (within D-14's KISS posture),
not a goal failure. Frontmatter `status` advanced `gaps_found` → `verified`; the
original gap record is preserved as `gaps_historical` for the audit trail.

_Reconciled: 2026-05-29T03:05:00Z — Claude (verify-work post-UAT gate)_
