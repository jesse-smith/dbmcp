---
phase: quick-260528-tmy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_server/schema_tools.py
  - tests/unit/test_async_tools.py
autonomous: true
requirements: [T-15-08, T-15-12]

must_haves:
  truths:
    - "Passing a catalog to list_schemas on a non-Databricks connection returns status=error mentioning 'catalog'"
    - "list_schemas docstring states catalog is rejected (not ignored) on non-Databricks dialects"
    - "A boundary test proves the list_schemas catalog gate fires on MSSQL"
    - "A boundary test proves the list_tables catalog gate fires on MSSQL"
  artifacts:
    - path: "src/mcp_server/schema_tools.py"
      provides: "list_schemas catalog gate + corrected docstring"
      contains: "_assert_catalog_allowed(catalog, dialect)"
    - path: "tests/unit/test_async_tools.py"
      provides: "list_schemas + list_tables catalog-gate boundary tests"
      contains: "test_list_schemas_catalog_on_mssql_errors"
  key_links:
    - from: "src/mcp_server/schema_tools.py:list_schemas._sync_work"
      to: "src/db/identifiers.py:_assert_catalog_allowed"
      via: "dialect fetch + gate call"
      pattern: "_assert_catalog_allowed\\(catalog, dialect\\)"
---

<objective>
Close open security threats T-15-08 and T-15-12: the D-07 catalog gate is wired into every catalog-accepting tool EXCEPT `list_schemas`. A catalog argument silently passes through `list_schemas` on non-Databricks dialects instead of being rejected at the tool boundary.

Purpose: Enforce the D-07 invariant (catalog rejected when `dialect.max_identifier_depth < 3`) uniformly across all tools, and close the test-coverage gap on `list_tables` (gated in code, untested).

Output: Gated `list_schemas`, corrected docstring, and two new boundary tests proving the gate fires on MSSQL for both `list_schemas` and `list_tables`.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/15-unified-identifier-resolver-cross-dialect/15-SECURITY.md

# Project convention: ALL Python tooling via `uv run` (uv run pytest, uv run ruff). Never bare python/python3/.venv.

<interfaces>
From src/db/identifiers.py (already imported in schema_tools.py:14):
```python
def _assert_catalog_allowed(catalog: str | None, dialect) -> None:
    # Raises ValueError when `catalog` is set and dialect.max_identifier_depth < 3.
```

Established gate pattern (src/mcp_server/schema_tools.py:355-357, inside list_tables._sync_work):
```python
conn_manager = get_connection_manager()
dialect = conn_manager.get_dialect(connection_id)
_assert_catalog_allowed(catalog, dialect)
```
list_schemas already has an outer `except ValueError` (schema_tools.py:282) that converts the raised
ValueError into a status=error response — no new error handling is required.

Established test pattern (tests/unit/test_async_tools.py:399-454, TestCatalogGateBoundary):
```python
def _patch_cm(module, dialect, engine=None): ...  # patches module.get_connection_manager
# Each test: factory, _ = _patch_cm(<module>, MssqlDialect()); await tool(..., catalog="x")
# assert "error" in result and "catalog" in result.lower()
```
MssqlDialect is already imported in the test file. list_schemas/list_tables live in the
`schema_tools` module — import `from src.mcp_server import schema_tools` and patch that module.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Wire D-07 catalog gate into list_schemas and flip its docstring</name>
  <files>src/mcp_server/schema_tools.py</files>
  <action>
    In `list_schemas._sync_work` (currently schema_tools.py:263-277), prepend the dialect fetch and
    gate call before the `_get_metadata_service(connection_id)` line, mirroring the list_tables pattern
    at schema_tools.py:355-357 (per D-07 / closing T-15-08):
      conn_manager = get_connection_manager()
      dialect = conn_manager.get_dialect(connection_id)
      _assert_catalog_allowed(catalog, dialect)
    `_assert_catalog_allowed` is already imported (schema_tools.py:14); `get_connection_manager` is
    already used by list_tables in the same module, so no new imports are needed. The existing outer
    `except ValueError` (schema_tools.py:282) already converts the raised ValueError into a status=error
    response — do NOT add new error handling.

    Then flip the docstring at schema_tools.py:247 from `Ignored for non-Databricks dialects.` to match
    the list_tables wording at schema_tools.py:327: `Rejected on non-Databricks dialects (raises an error).`

    Do NOT touch src/db/metadata.py's silent-ignore behavior — out of scope; the tool-boundary gate is
    the mitigation and the catalog never reaches SQL on the non-Databricks path.
  </action>
  <verify>
    <automated>uv run ruff check src/mcp_server/schema_tools.py && grep -q "Rejected on non-Databricks dialects (raises an error)." src/mcp_server/schema_tools.py && uv run python -c "import ast,sys; src=open('src/mcp_server/schema_tools.py').read(); t=ast.parse(src); fn=next(n for n in ast.walk(t) if isinstance(n,ast.AsyncFunctionDef) and n.name=='list_schemas'); assert '_assert_catalog_allowed' in ast.get_source_segment(src,fn), 'gate not wired into list_schemas'; print('OK')"</automated>
  </verify>
  <done>
    list_schemas._sync_work fetches the dialect and calls _assert_catalog_allowed(catalog, dialect)
    before metadata access; the catalog docstring reads "Rejected on non-Databricks dialects (raises an
    error)."; ruff reports no new warnings on the file.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add catalog-gate boundary tests for list_schemas and list_tables</name>
  <files>tests/unit/test_async_tools.py</files>
  <action>
    Extend `TestCatalogGateBoundary` (tests/unit/test_async_tools.py:408) with two new async tests,
    following the existing test pattern in that class (closing the test half of T-15-12 and proving
    the T-15-08 fix):

    - `test_list_schemas_catalog_on_mssql_errors`: `from src.mcp_server import schema_tools`;
      `factory, _ = _patch_cm(schema_tools, MssqlDialect())`; `with factory:` await
      `schema_tools.list_schemas(connection_id="c", catalog="x")`; assert `"error" in result` and
      `"catalog" in result.lower()`.
    - `test_list_tables_catalog_on_mssql_errors`: same shape, await
      `schema_tools.list_tables(connection_id="c", catalog="x")` (default args otherwise); same asserts.

    `_patch_cm` and `MssqlDialect` are already in the file — no new imports. Match the existing
    no-`get_config`-patch form used by the analysis_tools tests in this class (list_schemas/list_tables
    do not call get_config on the gate path; the gate raises before metadata access).
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_async_tools.py -k "CatalogGate and (list_schemas or list_tables)" -q && uv run ruff check tests/unit/test_async_tools.py && uv run pytest -q</automated>
  </verify>
  <done>
    Both new tests pass (catalog on MSSQL returns an error mentioning "catalog"); the full suite passes
    with no regressions; ruff reports no new warnings on the test file.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP client → list_schemas tool | Untrusted `catalog` argument crosses into metadata introspection |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-08 | Elevation of Privilege | list_schemas (catalog arg) | mitigate | Wire `_assert_catalog_allowed(catalog, dialect)` at tool boundary; reject catalog when `dialect.max_identifier_depth < 3` (Task 1) |
| T-15-12 | Information Disclosure | list_tables catalog gate (untested) | mitigate | Add boundary test proving the existing list_tables code gate fires on MSSQL (Task 2) |

No package installs in this plan — no T-{phase}-SC checkpoint required.
</threat_model>

<verification>
- `uv run pytest tests/unit/test_async_tools.py -k CatalogGate` passes including the two new tests.
- `uv run pytest` full suite passes (no regressions).
- `uv run ruff check src/mcp_server/schema_tools.py tests/unit/test_async_tools.py` reports no new warnings (the pre-existing src/metrics.py warning is out of scope and unaffected).
- `grep` confirms the corrected docstring wording in schema_tools.py.
</verification>

<success_criteria>
- list_schemas rejects a catalog argument on non-Databricks dialects with status=error (T-15-08 closed).
- list_schemas docstring accurately states the catalog is rejected, not ignored.
- Boundary tests exist and pass for both list_schemas and list_tables catalog gates (T-15-12 closed).
- Full test suite green; no new ruff warnings.
</success_criteria>

<output>
Create `.planning/quick/260528-tmy-fix-open-threats-t-15-08-t-15-12-add-d-0/260528-tmy-SUMMARY.md` when done.
</output>
