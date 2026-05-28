---
phase: 15-unified-identifier-resolver-cross-dialect
reviewed: 2026-05-28T23:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/db/dialects/databricks.py
  - src/db/dialects/generic.py
  - src/db/dialects/mssql.py
  - src/db/dialects/protocol.py
  - src/db/identifiers.py
  - src/db/metadata.py
  - src/db/query.py
  - src/mcp_server/analysis_tools.py
  - src/mcp_server/query_tools.py
  - src/mcp_server/schema_tools.py
findings:
  critical: 2
  warning: 5
  info: 3
  total: 10
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-05-28T23:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase 15 cross-dialect identifier resolver work: the new `src/db/identifiers.py` module (`resolve_identifier` + `_assert_catalog_allowed`), the D-07 catalog gate, the removal of the hardcoded `dbo` default across `metadata.py` / `query.py`, and the `@mcp.tool()` boundary wiring in `schema_tools.py`, `query_tools.py`, and `analysis_tools.py`.

The resolver module itself is well-constructed: depth checking via `len(parts)` (correctly avoiding the documented sqlglot attribute-folding pitfall), conflict detection, and the catalog gate all behave as designed under direct testing. The injection posture (quote_identifier downstream) is sound.

However, the `dbo`-default removal was incomplete: it introduced a NULL-schema path that two downstream call sites do not handle, producing broken SQL (`"None"."orders"`) or crashes for the generic dialect and the schema-less sampling case. Separately, the catalog gate (D-07) is applied inconsistently across tools — `list_schemas` silently drops a supplied catalog while every other namespace tool either gates or honors it — and the analysis tools resolve a catalog from a dotted `table_name` but then silently discard it, querying the wrong catalog. These are correctness/data-integrity defects, not style nits.

## Critical Issues

### CR-01: dbo-default removal leaves an unguarded NULL-schema path that builds invalid SQL in `get_sample_data`

**File:** `src/db/query.py:132-133` (else branch); regression surface also at `src/db/query.py:120-131`
**Issue:** The `dbo` default was removed (`schema_name: str = "dbo"` → `schema_name: str | None = None`), but the non-catalog else branch still does:

```python
full_table_name = f"{self._dialect.quote_identifier(schema_name)}.{self._dialect.quote_identifier(table_name)}"
```

When `schema_name` is `None`, `quote_identifier(None)` does **not** raise for the generic and Databricks dialects — it returns the literal quoted string. Verified:

- Generic: `quote_identifier(None)` → `'"None"'`, producing `"None"."orders"` — a query against a nonexistent schema literally named `None`.
- Databricks (catalog falsy → else branch): `quote_identifier(None)` → `` '`None`' ``, producing `` `None`.`orders` ``.
- MSSQL: `quote_identifier(None)` raises `AttributeError: 'NoneType' object has no attribute 'replace'` (uncaught — leaks as an unexpected exception, not a clean `ValueError`).

For the **generic dialect**, `resolve_identifier` returns `schema=None` whenever the user passes a bare table name (generic `default_schema` is `None`). The resolver does NOT backfill a schema, so this NULL reaches `get_sample_data` and silently corrupts the query. Pre-removal, the `"dbo"` default masked this. This is a real regression for any non-MSSQL connection sampling a bare table name.

**Fix:** Guard the schema-less case explicitly instead of quoting `None`. Build the table reference from only the parts that are present:

```python
elif self._dialect is None:
    full_table_name = table_name
elif catalog and self._dialect.name == "databricks":
    parts = [catalog, schema_name, table_name]
    full_table_name = ".".join(self._dialect.quote_identifier(p) for p in parts if p)
elif schema_name:
    full_table_name = (
        f"{self._dialect.quote_identifier(schema_name)}."
        f"{self._dialect.quote_identifier(table_name)}"
    )
else:
    # No schema: emit a bare quoted table name; let the connection default resolve it.
    full_table_name = self._dialect.quote_identifier(table_name)
```

(Apply the same `if p`/None-guard to the Databricks 3-part branch at lines 127-131, which also crashes/corrupts when `schema_name` is `None`.)

### CR-02: Analysis tools resolve a catalog from dotted `table_name` then silently discard it, querying the wrong catalog

**File:** `src/mcp_server/analysis_tools.py:251-266` (`find_pk_candidates`), `src/mcp_server/analysis_tools.py:393-419` (`find_fk_candidates`)
**Issue:** Both tools call `resolve_identifier(table_name, schema_name, catalog, dialect)` and then use only `resolved.table` and `resolved.schema`. `resolved.catalog` is never referenced. On Databricks, `resolve_identifier("othercat.sales.orders", None, None, dialect)` returns `catalog="othercat"` (verified). The tool then runs `inspector.get_table_names(schema="sales")` against the **connection's default catalog**, not `othercat`.

Consequences:
- If a same-named `sales.orders` exists in the default catalog, the tool silently profiles the **wrong table** — a data-integrity defect (results attributed to a table the caller did not ask for).
- If it does not exist, the tool returns a misleading "Table 'sales.orders' not found in schema 'sales'" while the table does exist in the catalog the user named.

`get_column_info` (lines 119-141) handles this correctly via the catalog-aware `MetadataService.table_exists` path; `find_pk_candidates` and `find_fk_candidates` do not. The inline comments in both tools acknowledge the Inspector binds to the default catalog, but the code accepts a 3-part name that implies a non-default catalog without rejecting it or honoring it.

**Fix:** Either (a) reject a non-default catalog in these two tools by raising `ValueError` when `resolved.catalog` is set and differs from the engine-bound catalog, so the caller gets a clear error instead of silent mis-targeting; or (b) thread `resolved.catalog` through the existence check (mirroring `get_column_info`) and into the discovery query. Option (a) is the smaller, safer change given the Inspector limitation:

```python
resolved = resolve_identifier(table_name, schema_name, catalog, dialect)
if resolved.catalog and resolved.catalog != _engine_catalog_or_none(engine):
    raise ValueError(
        f"Cross-catalog analysis is not supported here; "
        f"reconnect with catalog '{resolved.catalog}' as the default."
    )
```

## Warnings

### WR-01: `list_schemas` does not gate or honor catalog, silently dropping it on non-Databricks dialects

**File:** `src/mcp_server/schema_tools.py:263-277`; downstream `src/db/metadata.py:104-110`
**Issue:** `list_tables` (line 357) calls `_assert_catalog_allowed(catalog, dialect)`, `get_table_schema` and the analysis/query tools gate via `resolve_identifier`. But `list_schemas` passes `catalog` straight to `metadata_svc.list_schemas(...)`, and `metadata.list_schemas` only uses `catalog` when the dialect is Databricks — on MSSQL/generic the argument is silently ignored. A user who passes `catalog="x"` to `list_schemas` on MSSQL gets no error and no effect, contradicting the D-07 gate applied everywhere else and the module docstring in `identifiers.py` (lines 24-25) which explicitly claims `list_schemas` reuses `_assert_catalog_allowed`. The documented invariant is violated.

**Fix:** Add the gate in the `list_schemas` tool body, consistent with `list_tables`:

```python
def _sync_work():
    conn_manager = get_connection_manager()
    dialect = conn_manager.get_dialect(connection_id)
    _assert_catalog_allowed(catalog, dialect)
    metadata_svc = _get_metadata_service(connection_id)
    ...
```

### WR-02: `execute_query` builds `QueryService` with no dialect, diverging from `get_sample_data` and weakening dialect-specific safety

**File:** `src/mcp_server/query_tools.py:201`
**Issue:** `get_sample_data` constructs `QueryService(engine, dialect=dialect, metadata_service=metadata_svc)` (line 100), but `execute_query` constructs `QueryService(engine)` (line 201) with no dialect. `QueryService.__init__` then auto-infers via `get_dialect(engine.dialect.name)`, which raises `ValueError` for generic backends (sqlite/postgresql are not registry keys — verified), leaving `_dialect = None`. With `_dialect = None`:
- `parse_query_type` falls back to `sqlglot_dialect="tsql"` (line 336) even for a Postgres/Databricks connection — wrong parser dialect.
- `safe_operational_commands` falls back to empty `frozenset()`, so a Databricks connection inferred as `None` (or any path where inference fails) would block `SHOW`/`DESCRIBE`/`EXPLAIN` that the explicit-dialect path allows.

This is an inconsistency that makes `execute_query` behave differently from every other tool, which all pass the resolved dialect from `conn_manager.get_dialect(connection_id)`.

**Fix:** Pass the connection's dialect explicitly, matching `get_sample_data`:

```python
conn_manager = get_connection_manager()
engine = conn_manager.get_engine(connection_id)
dialect = conn_manager.get_dialect(connection_id)
query_svc = QueryService(engine, dialect=dialect)
```

### WR-03: `_build_count_query` produces invalid SQL when the original query ends with a semicolon

**File:** `src/db/query.py:729-743`
**Issue:** `_build_count_query` wraps the comment-stripped query in a subquery: `SELECT COUNT(*) FROM ({cleaned}) AS count_subquery`. `_remove_sql_comments` does not strip a trailing `;`, so `SELECT * FROM t;` yields `SELECT COUNT(*) FROM (SELECT * FROM t;) AS count_subquery` (verified) — a syntax error. The failure is swallowed (`except SQLAlchemyError: pass`, line 724), so `total_rows_available` silently returns `None` and the `limited`/`rows_available` metadata is wrong whenever a limited result is produced by a semicolon-terminated query. Not a crash, but a silent loss of the "more rows available" signal.

**Fix:** Strip a trailing semicolon before wrapping:

```python
cleaned = self._remove_sql_comments(query_text.strip()).rstrip(";").strip()
```

### WR-04: `find_fk_candidates` source-column lookup is case-sensitive while the rest of the identifier path is case-insensitive

**File:** `src/mcp_server/analysis_tools.py:412-419`
**Issue:** The source column is matched with `c["name"] == column_name` (exact case). Elsewhere the codebase treats SQL identifiers case-insensitively (e.g. `QueryService._validate_identifier` lower-cases for lookup). On SQL Server's default case-insensitive collation, a user passing `customerid` for a column declared `CustomerID` gets a spurious "Column not found" from `find_fk_candidates` even though the column exists and the query engine would resolve it. Inconsistent and surprising.

**Fix:** Match case-insensitively and use the metadata casing:

```python
col_info = next(
    (c for c in columns if c["name"].lower() == column_name.lower()), None
)
```

### WR-05: `get_table_schema` hardcodes `"dbo"` as the default referred schema for foreign keys, re-introducing the dialect-specific default the phase set out to remove

**File:** `src/db/metadata.py:919`
**Issue:** In the FK serialization, `"target_schema": fk.get("referred_schema", "dbo")`. For a Databricks or generic connection where `referred_schema` is absent/None, this stamps the MSSQL-specific literal `"dbo"` onto a non-MSSQL relationship — exactly the kind of hardcoded `dbo` assumption this phase removed elsewhere. Misleading output for cross-dialect users.

**Fix:** Fall back to the actual source schema (or `None`) rather than the MSSQL literal:

```python
"target_schema": fk.get("referred_schema") or schema_name,
```

## Info

### IN-01: `inject_row_limit` LIMIT-injection uses fragile regex/string surgery rather than the sqlglot AST already in use

**File:** `src/db/query.py:406-485`
**Issue:** The non-MSSQL path uses `re.search(r'\bLIMIT\s+\d+', ...)` and trailing-semicolon string splicing, and the CTE TOP-injection path (`_inject_top_in_cte`) hand-walks parentheses to find the final SELECT. `parse_query_type` already parses the query with sqlglot; the limit injection could reuse the AST (`exp.Limit` / `.limit()`) for correctness on edge cases (LIMIT inside a subquery, `LIMIT` with parameter, comments between tokens). Not a confirmed bug, but a maintainability/robustness smell given an AST is already available.
**Fix:** Consider injecting the limit via sqlglot's `expression.limit(n)` on the parsed top-level statement and re-serializing with the dialect, eliminating the regex/paren-walking heuristics.

### IN-02: Resolver `dialect` parameter is untyped (`dialect` with no annotation)

**File:** `src/db/identifiers.py:45,60-65`
**Issue:** `_assert_catalog_allowed(catalog, dialect)` and `resolve_identifier(..., dialect)` take an untyped `dialect`. The module relies on `dialect.max_identifier_depth`, `.name`, `.sqlglot_dialect`, `.default_schema`. A `"DialectStrategy"` annotation (via `TYPE_CHECKING` import, as `metadata.py` and `query.py` already do) would document the contract and catch mismatches.
**Fix:** Annotate `dialect: "DialectStrategy"` and add the `TYPE_CHECKING` import of `src.db.dialects.protocol.DialectStrategy`.

### IN-03: Inconsistent "not found" error message shapes across tools

**File:** `src/mcp_server/schema_tools.py:488`, `src/mcp_server/analysis_tools.py:140,265,407`
**Issue:** `get_table_schema` emits `Table '{schema}.{table}' not found`, while the analysis tools emit `Table '{table}' not found in schema '{schema}'`. Minor inconsistency in the user-facing error surface for the same logical condition; harmless but worth unifying for predictable client handling.
**Fix:** Standardize on one phrasing across the namespace tools.

---

_Reviewed: 2026-05-28T23:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
