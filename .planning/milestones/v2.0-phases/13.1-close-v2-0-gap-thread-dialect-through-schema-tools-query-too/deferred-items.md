# Phase 13.1 Deferred Items


## Resolved

### From 13.1-02 (WIRING-02 get_sample_data dialect threading)

**test_get_sample_data_mcp_tool** — `tests/integration/test_sample_data.py:155+`
- Marked @pytest.mark.skip with rationale after WIRING-02 fix.
- Root cause: `QueryService._build_top_query` (src/db/query.py:183-188) uses
  `self._dialect is None` as a proxy for SQLite, emitting `SELECT TOP` for any
  non-None dialect. This predates the v2.0 dialect refactor. GenericDialect
  against a SQLite engine therefore produces SQL Server syntax that SQLite
  rejects. Pre-WIRING-02 the test worked accidentally because the auto-infer
  path fell through to `_dialect = None` for SQLite engines (sqlite not in
  registry). Post-WIRING-02 we pass the registered GenericDialect explicitly.
- Follow-up: have GenericDialect provide dialect-correct TOP/LIMIT sampling
  queries (or move sample-SQL generation into DialectStrategy). Out of scope
  for 13.1-02 (source fix is 3 lines + regression test).

**Resolved 2026-05-06 (quick 260506-n8s)**: DialectStrategy now exposes
`build_sample_query`; QueryService delegates. MSSQL emits TOP, Databricks and
Generic emit LIMIT. The integration test above has been unskipped and passes
against the sqlite-flavored GenericDialect path. See the GREEN commit from
task 2 of the 260506-n8s plan.
