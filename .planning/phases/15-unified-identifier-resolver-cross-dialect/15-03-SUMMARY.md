---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 03
subsystem: db/identifiers
tags: [identifier-resolution, cross-dialect, sqlglot, tdd]
requires: [15-01]
provides:
  - "resolve_identifier(table_name, schema_name, catalog, dialect) -> ResolvedIdentifier"
  - "ResolvedIdentifier frozen dataclass (catalog, schema, table)"
  - "_assert_catalog_allowed(catalog, dialect) shared gate"
  - "CATALOG_GATE_MESSAGE module-level template"
affects:
  - "Plan 04 (get_sample_data / get_column_info catalog param + resolver adoption)"
  - "Plan 05 (list_schemas, get_table_schema, list_tables resolver adoption)"
  - "Plan 06 (find_pk_candidates / find_fk_candidates namespace-aware, catalog gate reuse)"
tech-stack:
  added: []
  patterns:
    - "Pure standalone module under src/db/ (mirrors src/db/validation.py)"
    - "Depth measured via len(Table.parts), never Table.name/db/catalog (RESEARCH Pitfall 1)"
    - "Shared catalog gate (Rule of Three: resolver + list_schemas + find_pk/fk)"
key-files:
  created:
    - src/db/identifiers.py
    - tests/unit/test_identifiers.py
  modified: []
decisions:
  - "Catalog gate runs BEFORE depth check so a catalog on a shallow dialect reports the gate message, not a depth error (RESEARCH skeleton ordering)"
  - "Conflict detection is disagreement-only (D-04): redundant-but-consistent params are allowed"
  - "ParseError normalized to ValueError (A1) so it maps through the existing tool-boundary except ValueError path"
metrics:
  duration: ~12m
  completed: 2026-05-28
  tasks: 2
  files: 2
---

# Phase 15 Plan 03: Cross-Dialect Identifier Resolver Summary

Built `src/db/identifiers.py` — a pure, dialect-agnostic identifier resolver exporting `resolve_identifier()`, the frozen `ResolvedIdentifier(catalog, schema, table)` dataclass, and a shared `_assert_catalog_allowed` + `CATALOG_GATE_MESSAGE` gate — via strict RED→GREEN TDD. Depth is measured by `len(Table.parts)` (the only correct check; sqlglot attributes silently swallow over-depth segments).

## What Was Built

- **`ResolvedIdentifier`** (D-02): frozen dataclass with required `catalog: str | None`, `schema: str | None`, `table: str`.
- **`resolve_identifier(table_name, schema_name, catalog, dialect)`**: parse via `sqlglot.to_table(..., dialect=dialect.sqlglot_dialect)` → catalog-gate (D-07) → depth-check via `len(parts)` (IDENT-03) → right-to-left part mapping → disagreement-only conflict detection (IDENT-04/D-04) → default-schema fill (IDENT-07).
- **`_assert_catalog_allowed(catalog, dialect)`** + module-level **`CATALOG_GATE_MESSAGE`**: shared gate raising `ValueError` iff `catalog` is truthy and `dialect.max_identifier_depth < 3`. Reused by the resolver internally and exported for the table_name-less tools (list_schemas, find_pk/fk_candidates).
- **`tests/unit/test_identifiers.py`**: 29-test parametrized matrix grouped into `TestDepthParsing`, `TestConflictDetection`, `TestCatalogGate`, `TestDefaultSchema`, `TestMalformedInput`, `TestResolvedIdentifier`, using real `MssqlDialect` / `DatabricksDialect` / `GenericDialect` instances.

## TDD Gate Compliance

- **RED** (88ee291): `test(15-03): add failing resolver matrix` — failed with `ModuleNotFoundError: No module named 'src.db.identifiers'` (verified before implementation).
- **GREEN** (c408fab): `feat(15-03): implement cross-dialect resolve_identifier` — full matrix passes (29/29).
- **REFACTOR**: not needed; implementation is already KISS-compliant (single linear function, shared gate extracted from the start).

Gate sequence valid: a `test(...)` commit precedes the `feat(...)` commit.

## Verification Results

- `uv run pytest tests/unit/test_identifiers.py` → 29 passed.
- `-k depth` → 11 passed; `-k conflict` → 4 passed.
- `grep -c 'len(.*parts)' src/db/identifiers.py` → 6 (Pitfall-1 depth check present).
- `grep -q 'ParseError'` and `grep -q '_assert_catalog_allowed'` → both present.
- `uv run ruff check src/db/identifiers.py tests/unit/test_identifiers.py` → All checks passed.
- Related dialect/validation suites (237 tests) → all pass, no regressions.

## Deviations from Plan

None — plan executed exactly as written. No auth gates, no architectural changes.

## Known Stubs

None. The resolver is fully wired; adoption by the seven tools happens in Plans 04/05/06.

## Threat Flags

None. The resolver introduces no new trust boundary: it decomposes user-supplied
identifier strings into parts that continue to flow through the existing
`dialect.quote_identifier` injection defense (T-15-04 disposition: mitigate-downstream,
unchanged). `sqlglot.ParseError` is caught and normalized to `ValueError` (T-15-05).

## Self-Check: PASSED

- FOUND: src/db/identifiers.py
- FOUND: tests/unit/test_identifiers.py
- FOUND commit: 88ee291 (RED)
- FOUND commit: c408fab (GREEN)
