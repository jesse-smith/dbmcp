---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - src/db/connection.py
  - src/mcp_server/schema_tools.py
  - src/mcp_server/query_tools.py
  - src/mcp_server/analysis_tools.py
  - tests/unit/test_connection.py
  - tests/unit/test_query_timeout.py
  - tests/unit/test_async_tools.py
autonomous: true
requirements: [TIMEOUT-01, ASYNC-01]

must_haves:
  truths:
    - "Queries that exceed the timeout threshold are terminated by the driver, not left hanging"
    - "Long-running DB calls do not block the MCP async event loop"
    - "Query timeout is configurable per-connection with a sensible default (30s)"
    - "Existing tests continue to pass (no regressions)"
  artifacts:
    - path: "src/db/connection.py"
      provides: "query_timeout parameter on PoolConfig and connect(), passed to pyodbc via connect_args"
      contains: "SQL_ATTR_QUERY_TIMEOUT"
    - path: "src/mcp_server/schema_tools.py"
      provides: "async wrappers using asyncio.to_thread for all sync DB calls"
      contains: "asyncio.to_thread"
    - path: "src/mcp_server/query_tools.py"
      provides: "async wrappers using asyncio.to_thread for all sync DB calls"
      contains: "asyncio.to_thread"
    - path: "src/mcp_server/analysis_tools.py"
      provides: "async wrappers using asyncio.to_thread for all sync DB calls"
      contains: "asyncio.to_thread"
    - path: "tests/unit/test_query_timeout.py"
      provides: "Tests for query timeout configuration"
    - path: "tests/unit/test_async_tools.py"
      provides: "Tests verifying MCP tools use asyncio.to_thread"
  key_links:
    - from: "src/db/connection.py"
      to: "pyodbc connect_args"
      via: "SQL_ATTR_QUERY_TIMEOUT in create_engine connect_args or creator attrs_before"
      pattern: "SQL_ATTR_QUERY_TIMEOUT"
    - from: "src/mcp_server/*.py"
      to: "src/db/*.py"
      via: "asyncio.to_thread wrapping sync engine.connect() blocks"
      pattern: "asyncio\\.to_thread"
---

<objective>
Add query execution timeouts and async DB execution to prevent the MCP event loop from blocking.

Purpose: During UAT, `get_column_info` on a large table hung for 2+ minutes, blocking ALL other MCP tool calls. Two fixes:
1. pyodbc query timeout so queries can't hang forever
2. asyncio.to_thread() wrappers so sync DB calls don't block the event loop

Output: Modified connection.py with query timeout support, all 3 tool modules wrapped with asyncio.to_thread, tests for both behaviors.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/db/connection.py
@src/mcp_server/schema_tools.py
@src/mcp_server/query_tools.py
@src/mcp_server/analysis_tools.py
@src/db/query.py
@src/db/metadata.py
@tests/unit/test_connection.py

<interfaces>
<!-- Key types and contracts the executor needs -->

From src/db/connection.py:
```python
@dataclass
class PoolConfig:
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True

class ConnectionManager:
    def __init__(self, pool_config: PoolConfig | None = None): ...
    def connect(self, server, database, ..., connection_timeout=30, ...) -> Connection: ...
    def _create_engine(self, odbc_conn_str, authentication_method, tenant_id) -> Engine: ...
    def get_engine(self, connection_id) -> Engine: ...
```

From src/db/query.py:
```python
class QueryService:
    def __init__(self, engine: Engine): ...
    # All methods are sync, use engine.connect() internally
```

From src/db/metadata.py:
```python
class MetadataService:
    def __init__(self, engine: Engine): ...
    # All methods are sync, use engine.connect() internally
```

MCP tool pattern (all 3 tool files):
```python
@mcp.tool()
async def tool_name(...) -> str:
    # Currently: gets engine, calls sync service methods directly
    # Target: wrap sync blocks in asyncio.to_thread()
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add query timeout to connection engine creation</name>
  <files>src/db/connection.py, tests/unit/test_query_timeout.py, tests/unit/test_connection.py</files>
  <behavior>
    - Test 1: PoolConfig has query_timeout field with default 30
    - Test 2: ConnectionManager.connect() accepts query_timeout parameter (5-300 range, same as connection_timeout)
    - Test 3: _create_engine passes SQL_ATTR_QUERY_TIMEOUT via connect_args for standard auth (non-Azure AD Integrated)
    - Test 4: _create_engine passes SQL_ATTR_QUERY_TIMEOUT via attrs_before for Azure AD Integrated auth (alongside existing SQL_COPT_SS_ACCESS_TOKEN)
    - Test 5: query_timeout=0 means no timeout (driver default)
    - Test 6: Invalid query_timeout (<0 or >300) raises ValueError
  </behavior>
  <action>
    1. Add `query_timeout: int = 30` to PoolConfig dataclass.

    2. Add `query_timeout: int = 30` parameter to `ConnectionManager.connect()`. Validate range: 0 (no timeout) or 5-300. Pass it through to `_create_engine`.

    3. In `_create_engine`, for the standard (non-Azure-AD-Integrated) path:
       - Add `connect_args={"attrs_before": {SQL_ATTR_QUERY_TIMEOUT: query_timeout}}` to the `create_engine()` call.
       - Import the constant: `SQL_ATTR_QUERY_TIMEOUT = 1005` (this is the ODBC constant, define it at module level near the existing SQL_COPT_SS_ACCESS_TOKEN import).
       - Note: pyodbc's `attrs_before` dict sets ODBC connection attributes before the connection is established. SQL_ATTR_QUERY_TIMEOUT is per-statement and respected by pyodbc on the connection level.

    4. For the Azure AD Integrated path (creator function):
       - The existing `attrs_before` already passes `SQL_COPT_SS_ACCESS_TOKEN`. Add `SQL_ATTR_QUERY_TIMEOUT: query_timeout` to the same dict.

    5. Update `_create_engine` signature to accept `query_timeout: int`.

    6. Write tests in tests/unit/test_query_timeout.py. Mock `create_engine` to capture kwargs and verify `connect_args` contains the timeout. For Azure path, mock `pyodbc.connect` to capture `attrs_before`.

    7. Existing tests in test_connection.py should still pass unchanged.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_query_timeout.py tests/unit/test_connection.py -x -v</automated>
  </verify>
  <done>PoolConfig.query_timeout exists with default 30. connect() accepts and validates query_timeout. Engine creation passes SQL_ATTR_QUERY_TIMEOUT to pyodbc for both standard and Azure AD Integrated auth paths. All new and existing tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wrap MCP tool sync DB calls in asyncio.to_thread</name>
  <files>src/mcp_server/schema_tools.py, src/mcp_server/query_tools.py, src/mcp_server/analysis_tools.py, tests/unit/test_async_tools.py</files>
  <behavior>
    - Test 1: Each MCP tool function calls asyncio.to_thread to execute its sync DB work
    - Test 2: The sync work passed to to_thread contains the actual DB operations (not just a passthrough)
    - Test 3: Tools still return correct TOON-encoded responses (mock the sync work)
    - Test 4: Error handling still works — ValueError and Exception paths still produce error responses
  </behavior>
  <action>
    1. For each tool module, extract the sync DB work into a local helper function, then call it via `asyncio.to_thread()`.

    **Pattern to apply in each tool function:**

    ```python
    import asyncio

    @mcp.tool()
    async def some_tool(connection_id: str, ...) -> str:
        # Parameter validation stays outside to_thread (fast, no I/O)
        ...

        def _sync_work():
            # All engine.connect(), service calls go here
            conn_manager = get_connection_manager()
            engine = conn_manager.get_engine(connection_id)
            with engine.connect() as connection:
                ...
            return response_dict

        try:
            result = await asyncio.to_thread(_sync_work)
            return encode_response(result)
        except ValueError as e:
            return encode_response({"status": "error", "error_message": str(e)})
        except Exception as e:
            return encode_response({"status": "error", "error_message": f"..."})
    ```

    2. **schema_tools.py** — 4 tools to wrap:
       - `connect_database`: Wrap `conn_manager.connect()`, `MetadataService(engine)`, `metadata_svc.list_schemas()`, and cache check in a `_sync_connect()` helper. Keep auth validation outside.
       - `list_schemas`: Wrap `_get_metadata_service()` + `list_schemas()` call.
       - `list_tables`: Wrap `_get_metadata_service()` + table query loop. Keep `_validate_list_tables_params()` outside (it's pure validation).
       - `get_table_schema`: Wrap `_get_metadata_service()` + `table_exists()` + `get_table_schema()`.

    3. **query_tools.py** — 2 tools to wrap:
       - `get_sample_data`: Wrap `QueryService(engine)` + `get_sample_data()`. Keep sample_size/method validation outside.
       - `execute_query`: Wrap `QueryService(engine)` + `execute_query()` + `get_query_results()`. Keep row_limit/query_text validation outside.

    4. **analysis_tools.py** — 3 tools to wrap:
       - `get_column_info`: Wrap entire `engine.connect()` block (table check + ColumnStatsCollector).
       - `find_pk_candidates`: Wrap entire `engine.connect()` block (table check + PKDiscovery).
       - `find_fk_candidates`: Wrap entire `engine.connect()` block (table check + column check + FKCandidateSearch).

    5. Write tests in tests/unit/test_async_tools.py:
       - For each tool, mock get_connection_manager and verify the tool awaits asyncio.to_thread.
       - Use `unittest.mock.patch("asyncio.to_thread")` or patch the service layer and verify the tool is properly async.
       - Alternatively: patch the sync services, call the tool with `await`, verify correct response shape.

    6. Run `uv run ruff check src/mcp_server/` to ensure no lint issues with the refactor.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_async_tools.py tests/ -x -v && uv run ruff check src/mcp_server/</automated>
  </verify>
  <done>All 9 MCP tools wrap their sync DB operations in asyncio.to_thread(). Parameter validation remains outside the thread (fast path). Error handling preserved. All 385+ existing tests pass. No ruff warnings in src/mcp_server/.</done>
</task>

</tasks>

<verification>
1. `uv run pytest tests/ -x` — full test suite passes (385+ tests, no regressions)
2. `uv run ruff check src/` — no new lint warnings
3. `grep -r "asyncio.to_thread" src/mcp_server/` — all 3 tool files use it
4. `grep -r "SQL_ATTR_QUERY_TIMEOUT" src/db/connection.py` — timeout configured
</verification>

<success_criteria>
- Query timeout of 30s configured by default on all new connections via pyodbc SQL_ATTR_QUERY_TIMEOUT
- All 9 MCP tools use asyncio.to_thread() for DB operations — event loop never blocked
- Full test suite passes with zero regressions
- No new lint warnings
</success_criteria>

<output>
After completion, create `.planning/quick/1-add-query-timeouts-and-async-db-executio/1-SUMMARY.md`
</output>
