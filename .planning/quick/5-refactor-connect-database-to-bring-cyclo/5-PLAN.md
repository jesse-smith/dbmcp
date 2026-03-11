---
phase: quick-5
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/models/schema.py
  - src/mcp_server/schema_tools.py
autonomous: true
requirements: [QUICK-5]

must_haves:
  truths:
    - "connect_database cyclomatic complexity is under 15"
    - "All existing tests pass with no regressions"
    - "scripts/check_complexity.py exits 0"
  artifacts:
    - path: "src/models/schema.py"
      provides: "ResolvedConnectionParams dataclass"
      contains: "class ResolvedConnectionParams"
    - path: "src/mcp_server/schema_tools.py"
      provides: "Refactored connect_database with extracted helpers"
      contains: "_resolve_connection_params"
  key_links:
    - from: "src/mcp_server/schema_tools.py::connect_database"
      to: "src/mcp_server/schema_tools.py::_resolve_connection_params"
      via: "function call returning ResolvedConnectionParams | error string"
      pattern: "_resolve_connection_params"
    - from: "src/mcp_server/schema_tools.py::_resolve_connection_params"
      to: "src/models/schema.py::ResolvedConnectionParams"
      via: "import and instantiation"
      pattern: "ResolvedConnectionParams"
---

<objective>
Refactor connect_database from cyclomatic complexity 48 down to under 15 by extracting
connection-resolution logic into private helpers and grouping resolved parameters into a dataclass.

Purpose: Fix CI failure — scripts/check_complexity.py currently fails with connect_database = 48.
Output: Passing complexity check, same behavior, cleaner code.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/mcp_server/schema_tools.py
@src/models/schema.py
@src/config.py
@scripts/check_complexity.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add ResolvedConnectionParams dataclass and extract helpers</name>
  <files>src/models/schema.py, src/mcp_server/schema_tools.py</files>
  <action>
1. In src/models/schema.py, add a dataclass after the AuthenticationMethod enum:

```python
@dataclass
class ResolvedConnectionParams:
    """Effective connection parameters after merging config + explicit args."""
    server: str
    database: str
    port: int
    authentication_method: str
    trust_server_cert: bool
    connection_timeout: int
    username: str | None
    password: str | None
    tenant_id: str | None
```

2. In src/mcp_server/schema_tools.py, add import for ResolvedConnectionParams from src.models.schema.

3. Extract a private function `_resolve_connection_params(...)` that takes the 10 connect_database parameters and returns either a ResolvedConnectionParams or an error dict (the encode_response-ready dict with status: "error"). This function absorbs:
   - The named-connection lookup and config merge (lines 125-179)
   - The required-field validation for server/database (lines 182-191)
   - The auth method parsing (lines 194-200)

   It should return `tuple[ResolvedConnectionParams | None, dict | None]` — either (params, None) on success or (None, error_dict) on failure.

   Inside this helper, further reduce branching by extracting a small helper `_merge_with_config(explicit_args, conn_cfg)` that handles the per-field "explicit if not None else config" merging plus password/tenant_id env-var resolution. This is the main complexity driver (each field is an if/else branch). Use a pattern like:

```python
def _pick(explicit, config_val):
    """Return explicit arg if provided, else config value."""
    return explicit if explicit is not None else config_val
```

   And for password/tenant_id that need resolve_env_vars, a small helper `_resolve_env_field(explicit, config_val)` that returns `(value, error_dict_or_none)`.

4. Simplify connect_database to:
   - Call `_resolve_connection_params(...)` — early return on error
   - Parse AuthenticationMethod from params.authentication_method (already validated by helper)
   - Define `_sync_connect()` closure using the resolved params
   - The existing try/except block (unchanged)

The goal is that connect_database itself has very few branches — just the one early-return on params error, the _sync_connect closure, and the 3 except clauses.

IMPORTANT: Do NOT change the public API signature of connect_database at all. Do NOT change any behavior — this is a pure refactor. The error messages, status codes, and response shapes must remain identical.
  </action>
  <verify>
    <automated>cd /Users/jsmith79/Documents/Projects/Ongoing/dbmcp && uv run pytest tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>All existing tests pass. ResolvedConnectionParams exists in schema.py. connect_database delegates to _resolve_connection_params.</done>
</task>

<task type="auto">
  <name>Task 2: Verify complexity is under 15 and lint is clean</name>
  <files>src/mcp_server/schema_tools.py</files>
  <action>
1. Run `uv run python scripts/check_complexity.py` — must exit 0.
2. Run `uv run ruff check src/` — must be clean (or only pre-existing warnings).
3. If complexity is still over 15, further decompose. The most likely remaining hotspot is the try/except block in connect_database (3 except clauses). If needed, extract the error-handling into a shared `_handle_tool_error(e, tool_name)` helper that returns the encoded error response — this also benefits list_schemas, list_tables, get_table_schema which have identical error handling patterns. Per user decision: "Consolidate the repeated try/except pattern into a shared helper."
4. If complexity check passes but _resolve_connection_params itself exceeds 15, break it further — the config-merge block is the densest branch cluster and should be its own function.
5. Iterate until `scripts/check_complexity.py` exits 0.
  </action>
  <verify>
    <automated>cd /Users/jsmith79/Documents/Projects/Ongoing/dbmcp && uv run python scripts/check_complexity.py && uv run ruff check src/ && uv run pytest tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>scripts/check_complexity.py exits 0 (all functions under 15). Ruff clean. All tests pass.</done>
</task>

</tasks>

<verification>
- `uv run python scripts/check_complexity.py` exits 0
- `uv run pytest tests/ -x -q` all pass
- `uv run ruff check src/` clean
- connect_database public API unchanged (same parameters, same return shape)
</verification>

<success_criteria>
- Complexity of connect_database is under 15
- No new helper function exceeds 15 complexity
- All 385+ existing tests pass
- Zero ruff warnings (beyond pre-existing metrics.py one)
</success_criteria>

<output>
After completion, create `.planning/quick/5-refactor-connect-database-to-bring-cyclo/5-SUMMARY.md`
</output>
