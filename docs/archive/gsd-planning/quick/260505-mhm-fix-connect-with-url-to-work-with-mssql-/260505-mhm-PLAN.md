---
phase: 260505-mhm
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/db/dialects/mssql.py
  - tests/test_mssql_dialect.py
  - src/mcp_server/schema_tools.py
autonomous: true
requirements:
  - TODO-2026-04-27-fix-connect-with-url-mssql
must_haves:
  truths:
    - "connect_database with sqlalchemy_url='mssql+pyodbc://...' succeeds against MSSQL (no KeyError: 'server')"
    - "URL query params authentication_method and trust_server_cert are parsed and applied"
    - "Existing kwargs-only path (connect_with_config) still works unchanged"
    - "Conflict behavior between URL and explicit kwargs is defined and documented"
  artifacts:
    - path: "src/db/dialects/mssql.py"
      provides: "MSSQLDialect.create_engine URL-aware entry point"
      contains: "sqlalchemy_url"
    - path: "tests/test_mssql_dialect.py"
      provides: "URL-parsing unit tests for MSSQLDialect.create_engine"
  key_links:
    - from: "src/db/connection.py:connect_with_url"
      to: "MSSQLDialect.create_engine"
      via: "sqlalchemy_url kwarg"
      pattern: "dialect\\.create_engine\\(sqlalchemy_url="
---

<objective>
Fix `connect_database(sqlalchemy_url=...)` for MSSQL. Currently `ConnectionManager.connect_with_url` passes `sqlalchemy_url` as a kwarg to `MSSQLDialect.create_engine`, but that method requires `server`/`database`/`authentication_method` kwargs and never reads the URL, causing `KeyError: 'server'`.

Purpose: Make URL-based connection a first-class MSSQL path (per todo Option 1).
Output: MSSQLDialect parses `sqlalchemy_url` via SQLAlchemy's `make_url()` when provided, deriving server/database/credentials/auth params from the URL. Kwargs-only path untouched. Tests cover both paths.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/todos/pending/2026-04-27-fix-connect-with-url-to-work-with-mssql.md
@src/db/dialects/mssql.py
@src/db/connection.py
@src/mcp_server/schema_tools.py

<interfaces>
<!-- Current MSSQLDialect.create_engine signature (kwargs-only, fails when sqlalchemy_url is passed): -->

```python
# src/db/dialects/mssql.py:101
def create_engine(self, **kwargs) -> Engine:
    # Expects: server, database, authentication_method (required)
    #          port, username, password, trust_server_cert, connection_timeout,
    #          query_timeout, pool_config, tenant_id, connection_id, disconnect_callback
```

How it's invoked from connect_with_url (src/db/connection.py ~321-374):

```python
engine = dialect.create_engine(
    sqlalchemy_url=sqlalchemy_url,
    query_timeout=query_timeout,
)
```

Enum to use when parsing auth from URL query string:

```python
# src/models/schema.py
class AuthenticationMethod(str, Enum):
    SQL = "sql"
    WINDOWS = "windows"
    AZURE_AD = "azure_ad"
    AZURE_AD_INTEGRATED = "azure_ad_integrated"
```

SQLAlchemy URL parser to use:

```python
from sqlalchemy.engine.url import make_url
url = make_url(sqlalchemy_url)
# url.host, url.port, url.database, url.username, url.password, url.query (dict)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add URL parsing branch to MSSQLDialect.create_engine</name>
  <files>src/db/dialects/mssql.py</files>
  <behavior>
    - When `sqlalchemy_url` kwarg is present, parse it with `sqlalchemy.engine.url.make_url()` and derive:
      - server <- url.host (required; raise ValueError if missing)
      - database <- url.database (required; raise ValueError if missing)
      - port <- url.port or 1433
      - username <- url.username
      - password <- url.password
      - authentication_method <- url.query.get("authentication_method") mapped to AuthenticationMethod enum; default AuthenticationMethod.SQL if username+password present, else AuthenticationMethod.WINDOWS
      - trust_server_cert <- url.query.get("trust_server_cert") parsed as bool ("true"/"1"/"yes" case-insensitive -> True; default False)
      - tenant_id <- url.query.get("tenant_id")
    - Conflict policy: URL values take precedence when `sqlalchemy_url` is provided. Explicit kwargs other than `sqlalchemy_url`, `query_timeout`, `pool_config`, `connection_id`, `disconnect_callback` are IGNORED when URL is present (log a debug message listing ignored keys). Document this in the docstring.
    - Preserve existing kwargs-only behavior: when `sqlalchemy_url` is absent, code path is unchanged (still reads server/database/authentication_method from kwargs).
    - Invalid `authentication_method` query value -> raise ValueError with accepted values listed.
  </behavior>
  <action>
    Modify `MSSQLDialect.create_engine` in src/db/dialects/mssql.py. Add a branch at the top (after the pyodbc import guard) that detects `sqlalchemy_url` in kwargs, parses it via `make_url()`, and populates a normalized kwargs dict that the existing code path consumes. Keep the existing kwargs-only logic intact — the URL branch should produce the same set of local variables (server, database, port, username, password, authentication_method, trust_server_cert, tenant_id) so the rest of the method runs unchanged. Add `from sqlalchemy.engine.url import make_url` to imports. Update the docstring to document the URL query params (`authentication_method`, `trust_server_cert`, `tenant_id`) and the conflict policy (URL wins). Do NOT change the method signature — still `**kwargs`.
  </action>
  <verify>
    <automated>uv run ruff check src/db/dialects/mssql.py</automated>
  </verify>
  <done>MSSQLDialect.create_engine accepts sqlalchemy_url kwarg, parses it via make_url, and produces the same engine as the kwargs-only path for equivalent inputs.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add URL-parsing tests for MSSQLDialect</name>
  <files>tests/test_mssql_dialect.py</files>
  <behavior>
    Test cases (mock `sa_create_engine` and `pyodbc` so no live DB is touched — only assert that the dialect derives correct parameters / constructs the expected ODBC string):
    - test_create_engine_parses_url_sql_auth: `mssql+pyodbc://user:pass@host:1433/mydb` -> server=host, database=mydb, port=1433, authentication_method=SQL, trust_server_cert=False.
    - test_create_engine_parses_url_windows_auth: `mssql+pyodbc://host/mydb?authentication_method=windows` -> authentication_method=WINDOWS, no username/password required.
    - test_create_engine_parses_url_trust_server_cert: `...?trust_server_cert=true` -> trust_server_cert=True. Also test "false", "1", "0".
    - test_create_engine_url_missing_host_raises: `mssql+pyodbc:///mydb` -> ValueError mentioning "server".
    - test_create_engine_url_missing_database_raises: `mssql+pyodbc://host/` -> ValueError mentioning "database".
    - test_create_engine_url_invalid_auth_method_raises: `...?authentication_method=bogus` -> ValueError listing accepted values.
    - test_create_engine_url_ignores_conflicting_kwargs: passing both `sqlalchemy_url=` and `server="other"` uses URL's host (URL wins).
    - test_create_engine_kwargs_only_path_unchanged: existing call with server/database/authentication_method kwargs (no sqlalchemy_url) still works — regression guard.
  </behavior>
  <action>
    Create or extend tests/test_mssql_dialect.py. Use `unittest.mock.patch` to mock `src.db.dialects.mssql.sa_create_engine` and inspect what arguments the dialect derived (either by capturing the ODBC connection string passed to sa_create_engine or by asserting on the `_build_odbc_connection_string` call via `patch.object`). Import `AuthenticationMethod` from `src.models.schema`. Follow existing test patterns in the tests/ directory (check one similar test file for fixture/style conventions before writing). Run with `uv run pytest tests/test_mssql_dialect.py -x -v`.
  </action>
  <verify>
    <automated>uv run pytest tests/test_mssql_dialect.py -x -v</automated>
  </verify>
  <done>All 8 test cases pass. No live DB connection attempted. Existing MSSQL tests still pass (`uv run pytest tests/ -k mssql -x`).</done>
</task>

<task type="auto">
  <name>Task 3: Update connect_database docstring for MSSQL URL contract</name>
  <files>src/mcp_server/schema_tools.py</files>
  <action>
    Update the docstring of `connect_database` in src/mcp_server/schema_tools.py (lines 87-112) to document the MSSQL-specific URL query parameters now supported:
    - `authentication_method`: sql | windows | azure_ad | azure_ad_integrated (default: sql if credentials present, else windows)
    - `trust_server_cert`: true | false (default: false)
    - `tenant_id`: Azure AD tenant (optional)

    Add a short example: `mssql+pyodbc://user:pass@host/db?authentication_method=sql&trust_server_cert=true`. Keep the existing generic-URL example for other dialects. Do not expand the docstring unnecessarily — 4-6 lines added.
  </action>
  <verify>
    <automated>uv run ruff check src/mcp_server/schema_tools.py</automated>
  </verify>
  <done>Docstring accurately describes the MSSQL URL contract including the three supported query params and one example.</done>
</task>

</tasks>

<verification>
- Full test suite passes: `uv run pytest tests/ -x`
- Lint clean: `uv run ruff check src/ tests/`
- Manual smoke (optional, user-gated): `connect_database(sqlalchemy_url="mssql+pyodbc://SVWTSTEM04/StemSoftClinicTest?authentication_method=windows&trust_server_cert=true")` returns status: success.
</verification>

<success_criteria>
- MSSQL URL-based connection succeeds (no KeyError).
- Kwargs-only path (named connections) continues to work — no existing tests regress.
- Conflict policy (URL wins) is both implemented and documented.
- New tests cover: SQL auth URL, Windows auth URL, trust_server_cert parsing, missing host, missing database, invalid auth method, conflicting kwargs, kwargs-only regression.
</success_criteria>

<output>
After completion, create `.planning/quick/260505-mhm-fix-connect-with-url-to-work-with-mssql-/260505-mhm-01-SUMMARY.md` capturing: files changed, test count added, final conflict-policy decision, and any deviations from the plan.
</output>
