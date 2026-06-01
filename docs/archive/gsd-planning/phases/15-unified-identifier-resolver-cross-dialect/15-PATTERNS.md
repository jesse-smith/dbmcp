# Phase 15: Unified identifier resolver (cross-dialect) - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 11 (2 new, 9 modified) + 1 new test file
**Analogs found:** 11 / 11 (every file has a strong in-repo analog; resolver parsing logic is net-new per CONTEXT D-01 but its module/dataclass shape, error mapping, and test shape all have analogs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/db/identifiers.py` (NEW) | utility (domain module) | transform (parse → ResolvedIdentifier) | `src/db/validation.py` (standalone pure-`sqlglot` domain module) + `src/config.py:44` (`@dataclass(frozen=True)`) | role-match (module shape) + exact (dataclass) |
| `src/db/dialects/protocol.py` (MODIFY) | protocol/config | n/a (capability advertisement) | existing `sqlglot_dialect` / `supports_indexes` `@property` blocks in same file | exact |
| `src/db/dialects/mssql.py` (MODIFY) | config (dialect impl) | n/a | own `sqlglot_dialect`/`supports_indexes` properties (lines 47-60) | exact |
| `src/db/dialects/databricks.py` (MODIFY) | config (dialect impl) | n/a | own `sqlglot_dialect`/`supports_indexes` properties (lines 89-102) | exact |
| `src/db/dialects/generic.py` (MODIFY) | config (dialect impl) | n/a | own `sqlglot_dialect`/`supports_indexes` properties (lines 49-62) | exact |
| `src/mcp_server/schema_tools.py` (MODIFY 3 tools) | controller (`@mcp.tool`) | request-response | `get_table_schema` in same file (lines 412-499) — already has `catalog` + `schema_name="dbo"` + `ValueError` boundary | exact |
| `src/mcp_server/query_tools.py` (MODIFY `get_sample_data`) | controller (`@mcp.tool`) | request-response | `get_table_schema` (schema_tools.py:412) for the `catalog` param + boundary; own `except ValueError` at :118 | exact |
| `src/mcp_server/analysis_tools.py` (MODIFY `get_column_info`) | controller (`@mcp.tool`) | request-response | `get_table_schema` (schema_tools.py:412); own `except ValueError` at :134 | exact |
| `src/db/metadata.py` (MODIFY: dbo sweep + consume resolved parts) | service | CRUD/read | own `get_columns` (line 731) for the `="dbo"` → `=None` edit; own Databricks routing (lines 101-110) | exact |
| `src/db/query.py` (MODIFY: dbo sweep) | service | read | own `sample_data` signature (line 81) | exact |
| `tests/unit/test_identifiers.py` (NEW) | test | n/a | `tests/unit/test_validation.py` (parametrized dialect-aware matrix with `ids=[...]`) | exact |

## Pattern Assignments

### `src/db/identifiers.py` (NEW — utility/transform)

**Module-shape analog:** `src/db/validation.py` — a standalone, pure-`sqlglot` domain module under `src/db/` with no class wrapper, exporting top-level functions. `identifiers.py` should mirror this: module docstring, `import sqlglot`, top-level `resolve_identifier(...)`, no service/class scaffolding (D-01).

**Frozen-dataclass analog:** `src/config.py` lines 44-67. The repo's established frozen-dataclass form (CONVENTIONS.md: "Dataclasses use CamelCase"):
```python
@dataclass(frozen=True)
class DefaultsConfig:
    """Configurable default parameter values."""

    query_timeout: int = 30
    text_truncation_limit: int = 1000
    sample_size: int = 5
    row_limit: int = 1000
```
Copy this exact form for `ResolvedIdentifier` (D-02):
```python
@dataclass(frozen=True)
class ResolvedIdentifier:
    """..."""
    catalog: str | None
    schema: str | None
    table: str
```
Note: `config.py` dataclasses use defaults; `ResolvedIdentifier` fields are required (no defaults) — order them `catalog, schema, table` so the required `table` is fine after the `| None` fields (all required, so no default-ordering constraint applies).

**Parsing core:** Use `sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)` then count `.parts` — see RESEARCH.md Pattern 1/2 and the resolver skeleton (lines 228-281). `validation.py` already establishes the precedent of calling sqlglot with a dialect string inside `src/db/`.

**Error handling:** Raise plain `ValueError` (D-05 — no new exception type). This is load-bearing: every `@mcp.tool` already maps `ValueError → error_message` (see Shared Patterns). Also catch `sqlglot.ParseError` and re-raise as `ValueError` (RESEARCH.md Pitfall 2 / A1) so malformed input flows through the same boundary.

---

### `src/db/dialects/protocol.py` + 3 impls (MODIFY — add two `@property`)

**Analog (same file, exact):** the existing `sqlglot_dialect` property declaration. In `protocol.py` (lines 35-38):
```python
@property
def sqlglot_dialect(self) -> str | None:
    """Sqlglot dialect name for query parsing (e.g., 'tsql', 'databricks'), or None for generic SQL."""
    ...
```
Add `default_schema` and `max_identifier_depth` in the same `@property` + `...` body + docstring style. Also extend the class-level docstring's `Properties:` block (lines 23-28) — that block enumerates each property and must list the two new ones to match the file's documentation convention.

**Impl analogs (exact, one per file):** each dialect already declares `sqlglot_dialect` as a one-line `return`. Copy that shape:

- `src/db/dialects/mssql.py` lines 47-50 →
  ```python
  @property
  def default_schema(self) -> str | None:
      """Default schema for MSSQL connections."""
      return "dbo"

  @property
  def max_identifier_depth(self) -> int:
      """Max dotted identifier parts (schema.table)."""
      return 2
  ```
- `src/db/dialects/databricks.py` lines 89-92 → `default_schema` returns `None` (no hardcoded `'main'` — RESEARCH anti-pattern), `max_identifier_depth` returns `3`.
- `src/db/dialects/generic.py` lines 49-52 → `default_schema` returns `None`, `max_identifier_depth` returns `1`.

Note `generic.py` uses an instance attr (`self._sqlglot_dialect`) for `sqlglot_dialect`; the two new properties are constant per dialect, so return literals directly (do not thread through `__init__`).

---

### `src/mcp_server/{schema_tools,query_tools,analysis_tools}.py` (MODIFY — 5 `@mcp.tool` fns)

**Canonical analog (exact):** `get_table_schema` in `schema_tools.py` lines 412-499. It is the only tool that already has ALL three ingredients the other four need: a `catalog: str | None = None` param, a `schema_name="dbo"` default to remove, and the `ValueError`→error-response boundary.

**Signature pattern** (lines 413-419) — note `catalog` is keyword-style `str | None = None` at the end:
```python
async def get_table_schema(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",      # <- D-11: change to `schema_name: str | None = None`
    include_indexes: bool = True,
    include_relationships: bool = True,
    catalog: str | None = None,    # <- copy this exact param onto get_sample_data + get_column_info (IDENT-05/06)
) -> str:
```

**Error-boundary pattern** (lines 487-499) — copy verbatim into the two tools that gain `catalog`; the three schema tools already have it:
```python
    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Error in get_table_schema")
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = f"Failed to get table schema: {str(e)}"
        return encode_response({"status": "error", "error_message": error_msg})
```
`query_tools.py:118` and `analysis_tools.py:134` already have `except ValueError as e: ... str(e)` — confirmed present, so the resolver's `ValueError` surfaces with no new plumbing.

**Resolver call site (D-03):** inside each tool's `_sync_work()` (the `asyncio.to_thread` worker), call `resolve_identifier(...)` BEFORE `_get_metadata_service`/`table_exists`, then pass `resolved.catalog/.schema/.table` down. Place the call inside `_sync_work` (not the async outer fn) so its `ValueError` is caught by the existing `except ValueError` wrapper — `get_table_schema` already runs all logic inside `_sync_work` (lines 468-485), copy that structure.

**Docstring change (D-07):** the `catalog` docstrings on the 3 schema tools read "Ignored for non-Databricks dialects" (schema_tools.py:326, :433; list_schemas:244-245 differs). Change to "rejected for non-Databricks dialects (raises an error)". Backward-incompatible — flagged.

---

### `src/db/metadata.py` (MODIFY — dbo sweep + consume resolved parts)

**dbo-default analog (exact, repeated):** every target site is a method signature with `schema_name: str = "dbo"`. Canonical (line 731):
```python
def get_columns(self, table_name: str, schema_name: str = "dbo") -> list[Column]:
```
D-11 edit at lines ~731, 781, 817, 833, 852, 1126: change `schema_name: str = "dbo"` → `schema_name: str | None = None`, and update each docstring's `Schema name (default: 'dbo')` accordingly. The tools now pass the resolved schema (already filled from `dialect.default_schema`), so the service stops defaulting.

**Out-of-scope flag:** `metadata.py:919` `fk.get("referred_schema", "dbo")` is a result-mapping default (FK target display), NOT a signature default — RESEARCH Pitfall 4 / A2 says leave it but note it. Do not change in SC4; record for a future dbo audit.

**Databricks catalog-routing analog (D-10 / passing resolved parts):** the established `dialect.name == "databricks"` gate (lines 101-110):
```python
if self._dialect and self._dialect.name == "databricks":
    effective_catalog = catalog or self._engine_catalog()
    result = self._list_schemas_databricks(connection_id, effective_catalog)
elif self._dialect and self._dialect.has_fast_row_counts:
    result = self._list_schemas_mssql(connection_id)
else:
    result = self._list_schemas_generic(connection_id)
```
This is the existing pattern for routing on dialect; resolved `catalog`/`schema=None` flow through it unchanged (generic `schema=None` → inspector default, no synthetic fallback).

---

### `src/db/query.py` (MODIFY — dbo sweep)

**Analog (exact):** `sample_data` signature at line 81:
```python
schema_name: str = "dbo",
```
D-11 edit: → `schema_name: str | None = None`, update docstring at :90. Downstream `quote_identifier` at :119 is UNCHANGED — it remains the SQL-safety boundary (resolver does not sanitize, RESEARCH §Security).

---

### `tests/unit/test_identifiers.py` (NEW — parametrized matrix, D-12)

**Analog (exact):** `tests/unit/test_validation.py` — the strongest parametrized, dialect-aware matrix in the suite (9 `@pytest.mark.parametrize` blocks, grouped by `class Test...`, with explicit `ids=[...]`). Copy its structure:

```python
class TestValidateQuerySafe:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            ...
        ],
        ids=[
            "simple_select",
            ...
        ],
    )
    def test_safe_query_passes(self, sql):
        result = validate_query(sql, dialect="tsql")
        assert result.is_safe is True
```

Model D-12's exhaustive matrix on this: parametrize over `(dialect, table_name, schema_name, catalog) → expected ResolvedIdentifier | raises ValueError`, grouped into `TestDepthParsing`, `TestConflictDetection`, `TestCatalogGate`, `TestDefaultSchema`, each with named `ids`. Use real dialect instances (`MssqlDialect()`, `DatabricksDialect()`, `GenericDialect()`) — `test_validation.py:9` imports `MssqlDialect` directly; `test_mssql_dialect.py` constructs `MssqlDialect()` and asserts property values.

**Tool-boundary thin test (D-12 second half):** extend `tests/unit/test_query_tools.py` and `tests/unit/test_analysis_tools.py` with a thin parametrized test asserting each tool routes through the resolver and surfaces `ValueError` as an error response. (RESEARCH Validation table marks these `⚠ extend`, and `test_identifiers.py` as ❌ Wave 0 / net-new.)

**Dialect-property tests (IDENT-07):** extend `test_mssql_dialect.py` / `test_databricks_dialect.py` / `test_generic_dialect.py` with `test_default_schema_*` and `test_max_identifier_depth_*` — model on `test_mssql_dialect.py:28` `test_sqlglot_dialect_is_tsql` (`assert dialect.sqlglot_dialect == "tsql"`).

## Shared Patterns

### ValueError → MCP error-response mapping
**Source:** `src/mcp_server/schema_tools.py` lines 490-491 (and `query_tools.py:118`, `analysis_tools.py:134`).
**Apply to:** all 5 tools — the resolver's `ValueError` (D-05) needs NO new plumbing; it lands here.
```python
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
```

### Dialect-owned capability via `@property`
**Source:** `src/db/dialects/protocol.py` lines 35-38 + the matching one-line `return` in each impl.
**Apply to:** `default_schema`, `max_identifier_depth` (D-08/D-09) on the Protocol + all 3 impls.

### sqlglot-with-dialect-string inside `src/db/`
**Source:** `src/db/validation.py` (`validate_query(sql, dialect="tsql")`, tested in `test_validation.py:46`).
**Apply to:** `identifiers.py` — `sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)`. The `dialect.sqlglot_dialect` property is the established our-dialect→parser-dialect mapping (mssql=`tsql`, databricks=`databricks`, generic=`None`/postgres/mysql/sqlite via `generic.py:_URL_SCHEME_TO_SQLGLOT`).

### Frozen dataclass
**Source:** `src/config.py:44` (`@dataclass(frozen=True) class DefaultsConfig`).
**Apply to:** `ResolvedIdentifier` (D-02).

### sync work in `_sync_work()` + `asyncio.to_thread`
**Source:** `src/mcp_server/schema_tools.py` lines 468-489 — all blocking metadata work goes in a nested `_sync_work()`, awaited via `asyncio.to_thread`, so exceptions surface to the outer `try/except`.
**Apply to:** place each tool's `resolve_identifier(...)` call inside `_sync_work` so its `ValueError` is caught.

## No Analog Found

None. Every file maps to an in-repo analog. The resolver's parsing *algorithm* is net-new (CONTEXT D-01: "No identifier parser exists today"), but its module shape, dataclass form, sqlglot-usage idiom, error-raising contract, and test structure all have exact analogs above — the planner should NOT fall back to RESEARCH.md generic patterns for structure, only for the verified sqlglot `to_table().parts` behavior (RESEARCH Patterns 1-2, Pitfalls 1-2).

## Metadata

**Analog search scope:** `src/db/`, `src/db/dialects/`, `src/mcp_server/`, `src/config.py`, `tests/unit/`
**Files scanned (read or gre+ targeted read):** protocol.py, mssql.py, databricks.py, generic.py, schema_tools.py, query_tools.py, analysis_tools.py, metadata.py, query.py, config.py, validation.py, test_validation.py, test_dialect_protocol.py, test_mssql_dialect.py
**Pattern extraction date:** 2026-05-28
