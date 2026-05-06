---
quick_id: 260506-n8s
status: complete
title: Fix dialect-blind SQL generation in QueryService sample-query methods
date: 2026-05-06
commits: [888ff20bd97b7b149c5a483ae55dc3f02082bf02, 3d75e42c2ed81dad5c93f455c72d366cf23f4b04, e4b0d52b377a183c8e8dae098bbe04e2ed441769]
files_modified:
  - src/db/dialects/protocol.py
  - src/db/dialects/mssql.py
  - src/db/dialects/databricks.py
  - src/db/dialects/generic.py
  - src/db/query.py
  - tests/unit/test_mssql_dialect.py
  - tests/unit/test_databricks_dialect.py
  - tests/unit/test_generic_dialect.py
  - tests/unit/test_query.py
  - tests/unit/test_dialect_protocol.py
  - tests/integration/test_sample_data.py
  - .planning/phases/13.1-close-v2-0-gap-thread-dialect-through-schema-tools-query-too/deferred-items.md
tests_added: 14
tests_passing: 964
---

# 260506-n8s Summary

Thread dialect-correct sample-query SQL generation through `DialectStrategy` and
collapse the three `QueryService._build_*_query` methods into thin delegations.
Databricks no longer receives `SELECT TOP (...)` (which triggers
PARSE_SYNTAX_ERROR); MSSQL output is byte-for-byte preserved; Generic dialect
uses `LIMIT` / `ORDER BY RANDOM()` / `ROW_NUMBER() ... LIMIT` for SQLite and
ANSI targets.

## Diff summary

- `src/db/dialects/protocol.py` — add `build_sample_query` to the protocol
  with a `TYPE_CHECKING` import of `SamplingMethod`.
- `src/db/dialects/mssql.py` — implement `build_sample_query` emitting
  `SELECT TOP (n)`, `TABLESAMPLE (n ROWS)`, and the existing
  `ROW_NUMBER() OVER (ORDER BY (SELECT NULL))` modulo SQL.
- `src/db/dialects/databricks.py` — implement `build_sample_query` emitting
  `LIMIT n`, `ORDER BY RAND() LIMIT n`, and a `ROW_NUMBER() ... LIMIT n` modulo.
- `src/db/dialects/generic.py` — implement `build_sample_query` emitting
  `LIMIT n`, `ORDER BY RANDOM() LIMIT n`, and a `ROW_NUMBER() ... LIMIT n`
  modulo (window `ORDER BY ROWID` when `_sqlglot_dialect == "sqlite"`, else
  `ORDER BY 1`).
- `src/db/query.py` — collapse the three `_build_*_query` methods to
  one-line dialect delegations; introduce `_sampling_dialect()` which returns
  a sqlite-flavored `GenericDialect` when `self._dialect is None` so legacy
  test paths still work.
- `tests/unit/test_dialect_protocol.py` — extend `_StubDialect` with
  `build_sample_query` so runtime protocol conformance still passes.
- `tests/integration/test_sample_data.py` — unskip
  `test_get_sample_data_mcp_tool` (the deferred item this fix resolves).
- `.planning/phases/13.1-.../deferred-items.md` — move the 13.1-02 item under a
  new `## Resolved` section with a 260506-n8s reference.

## TDD gate table

| Phase | Commit | Status |
|-------|--------|--------|
| RED    | 888ff20 `test(260506-n8s): add RED regression tests…`                         | 13 new tests fail against current source (no `build_sample_query`, no delegation) |
| GREEN  | 3d75e42 `fix(260506-n8s): delegate sample-query SQL generation to DialectStrategy` | All 13 RED tests pass; full suite 964 passed / 78 skipped |
| DOCS   | e4b0d52 `docs(260506-n8s): mark dialect-blind sample query item resolved`     | deferred-items.md updated; integration test unskipped and passing |

## Verification

- `uv run pytest -x -q` → `964 passed, 78 skipped in 44.36s`
- `uv run ruff check src/` → `All checks passed!`
- `grep "self._dialect is None" src/db/query.py` → 4 hits, none in
  `_build_top_query` / `_build_tablesample_query` / `_build_modulo_query`
  (remaining hits are schema-prefix handling in `get_sample_data`,
  identifier quoting in `_sanitize_identifier` / `_validate_identifier`, and
  row-limit injection in `inject_row_limit`).

Dialect-specific SQL shape assertions (all green):

- MSSQL `SELECT TOP (5) * FROM [dbo].[T]` preserved; TABLESAMPLE still
  `TOP (5) ... TABLESAMPLE (5 ROWS)`; modulo `TOP (5)` + `ROW_NUMBER()` +
  `ORDER BY (SELECT NULL)`.
- Databricks emits `LIMIT 5`; TABLESAMPLE falls back to
  `ORDER BY RAND() LIMIT 5`; never `TOP (` or `TABLESAMPLE`.
- Generic emits `LIMIT 5`; TABLESAMPLE uses `ORDER BY RANDOM()`; sqlite
  modulo uses `ORDER BY ROWID`.

## Deviations

- **Rule 2 (auto-fix)**: The dispatched worktree (`worktree-agent-a3dfc8db02363e218`)
  was pinned to a pre-v2.0 HEAD that did not contain `src/db/dialects/` at
  all — the plan's prerequisites were unreachable at the worktree tip. I
  reset the worktree branch to the plan's dispatch commit
  (`fd56d7a docs(260506-n8s): pre-dispatch plan for dialect-blind SQL generation fix`),
  which put the v2.0 dialect infrastructure back on disk and allowed the
  three TDD commits to land as specified. This is recorded per the GSD
  Rule 2 logging requirement.
- **Bonus**: `test_get_sample_data_mcp_tool` was unambiguously the
  deferred item this fix resolves; the skip was removed and the test
  passes. The plan permitted this contingent on the skip marker
  matching the resolved issue.
