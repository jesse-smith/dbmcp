---
phase: 260505-own
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/db/dialects/databricks.py
  - tests/unit/test_databricks_dialect.py
autonomous: true
requirements:
  - QUICK-260505-own-01
tags: [databricks, timeout, retry, connect-args, tdd]

must_haves:
  truths:
    - "An unreachable Databricks host fails in seconds (<=30s socket + <=2 retries), not minutes"
    - "Default connect_timeout of 30s is applied when caller does not supply connection_timeout"
    - "Retry cap of 2 attempts is applied by default"
    - "Caller-supplied connection_timeout overrides the 30s default"
    - "Caller-supplied connect_args entries override dialect defaults on a per-key basis"
    - "URL-mode call path receives the same connect_args treatment as kwargs-mode"
  artifacts:
    - path: "src/db/dialects/databricks.py"
      provides: "connect_args plumbed into sa_create_engine with _socket_timeout + _retry_stop_after_attempts_count"
      contains: "connect_args"
    - path: "tests/unit/test_databricks_dialect.py"
      provides: "Tests asserting connect_args kwargs passed to sa_create_engine"
      contains: "_socket_timeout"
  key_links:
    - from: "DatabricksDialect.create_engine"
      to: "sa_create_engine"
      via: "connect_args={'_socket_timeout': N, '_retry_stop_after_attempts_count': 2, ...}"
      pattern: "sa_create_engine.*connect_args"
---

<objective>
Plumb a bounded connect timeout and retry cap through `DatabricksDialect.create_engine` so unreachable hosts fail in seconds, not minutes.

Purpose: `connection_timeout` kwarg is currently preserved through URL-mode reconstruction but never reaches `databricks.sql.connect` — the connector's default retry/backoff hangs for minutes on bad hosts. Mirror MSSQL's 30s default but use the Databricks mechanism (`connect_args` on `create_engine`).

Output: `src/db/dialects/databricks.py` passes `connect_args={"_socket_timeout": <timeout>, "_retry_stop_after_attempts_count": 2}` to `sa_create_engine`, with user overrides honored. Tests lock in the behavior.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/db/dialects/databricks.py
@tests/unit/test_databricks_dialect.py
@.planning/quick/260505-o6n-fix-databricksdialect-url-parsing-parse-/260505-o6n-SUMMARY.md

<interfaces>
Current `DatabricksDialect.create_engine` (src/db/dialects/databricks.py:154-221) flow:
1. If `sqlalchemy_url` in kwargs → `kwargs = self._kwargs_from_url(sqlalchemy_url, kwargs)` (preserves `connection_timeout` among 5 runtime keys)
2. Extracts host/http_path/token/catalog/schema → rebuilds a `databricks://...` URL string
3. Final line: `return sa_create_engine(url, pool_pre_ping=True, echo=False)` — NO connect_args

`connection_timeout` is read off kwargs today only via `_kwargs_from_url`'s preserved-keys mechanism on the URL path. On the pure-kwargs path, `connection_timeout` sits in `kwargs` untouched and is equally ignored at the final `sa_create_engine` call. Both paths converge at line 221 — single injection point.

databricks-sql-connector honors these keys when forwarded via `connect_args`:
- `_socket_timeout` (seconds) — socket-level timeout
- `_retry_stop_after_attempts_count` (int) — max retry attempts

MSSQL sibling (src/db/dialects/mssql.py ~L176, L422) defaults `connection_timeout=30` and bakes it into the ODBC connection string — we mirror the 30s default, different mechanism.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — failing tests for connect_args timeout + retry cap</name>
  <files>tests/unit/test_databricks_dialect.py</files>
  <behavior>
    Add a `TestCreateEngineConnectArgs` class (or extend existing) with tests that patch `sa_create_engine` (same mock pattern as existing `TestCreateEngineFromUrl`) and assert on the `connect_args` kwarg it receives:

    - `test_default_connect_args_applied`: kwargs-mode call with host/http_path/token; assert `connect_args == {"_socket_timeout": 30, "_retry_stop_after_attempts_count": 2}`.
    - `test_connection_timeout_kwarg_overrides_default`: call with `connection_timeout=5`; assert `connect_args["_socket_timeout"] == 5` and retry cap still 2.
    - `test_user_connect_args_merged_user_wins_per_key`: call with `connect_args={"_socket_timeout": 10, "_retry_delay_max": 15}`; assert final `connect_args == {"_socket_timeout": 10, "_retry_stop_after_attempts_count": 2, "_retry_delay_max": 15}` (user's explicit `_socket_timeout` wins; dialect default retry cap still applied since user didn't set it; user's extra key preserved).
    - `test_user_retry_cap_override`: `connect_args={"_retry_stop_after_attempts_count": 5}` → final has `5`, not 2.
    - `test_connect_args_applied_on_url_path`: call with `sqlalchemy_url="databricks://token:T@host.com/main?http_path=/p"` and no `connection_timeout`; assert same defaults (30, 2) reach `sa_create_engine`.
    - `test_connect_args_url_path_respects_connection_timeout_kwarg`: URL mode + explicit `connection_timeout=7`; assert `_socket_timeout == 7`.

    Mock pattern (match existing tests):
    ```python
    with patch("src.db.dialects.databricks.sa_create_engine") as mock_ce:
        dialect.create_engine(host="h", http_path="/p", token="t")
        call_kwargs = mock_ce.call_args.kwargs
        assert call_kwargs["connect_args"] == {...}
    ```
  </behavior>
  <action>
    Write tests per the `<behavior>` block above. Run tests — they MUST fail (current code does not pass `connect_args` at all).

    Commit: `test(260505-own): add failing tests for Databricks connect_args timeout + retry cap`
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_databricks_dialect.py -v -k "connect_args or connection_timeout" 2>&1 | tail -30</automated>
  </verify>
  <done>New tests exist and fail with clear assertion errors indicating `connect_args` missing or empty in the mock call. RED commit created.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — inject connect_args with default + user override in create_engine</name>
  <files>src/db/dialects/databricks.py</files>
  <behavior>
    After RED is committed, modify `DatabricksDialect.create_engine` so the final `sa_create_engine` call includes merged `connect_args`.

    Algorithm (single injection point, after URL reconstruction, just before the return):
    ```python
    # Defaults: 30s socket timeout (mirrors MSSQL), cap retries at 2 so bad hosts fail fast.
    connection_timeout = kwargs.get("connection_timeout", 30)
    dialect_defaults = {
        "_socket_timeout": connection_timeout,
        "_retry_stop_after_attempts_count": 2,
    }
    # User-supplied connect_args win on matching keys; our defaults fill the gaps.
    user_connect_args = kwargs.get("connect_args") or {}
    merged_connect_args = {**dialect_defaults, **user_connect_args}

    return sa_create_engine(
        url,
        pool_pre_ping=True,
        echo=False,
        connect_args=merged_connect_args,
    )
    ```

    Notes:
    - `kwargs.get("connection_timeout", 30)` — default 30 when absent. Works for both kwargs-mode (user passed it directly) and URL-mode (preserved through `_kwargs_from_url`).
    - `{**defaults, **user_connect_args}` — user keys override dialect keys per-key. Extra user keys (e.g., `_retry_delay_max`) are preserved.
    - Do NOT modify `_kwargs_from_url`; it already preserves `connection_timeout`.
    - No MSSQL changes.
  </behavior>
  <action>
    Apply the diff described in `<behavior>`. Run the full test file. All new tests plus the existing 23 must pass.

    Also run ruff: `uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py`.

    Commit: `fix(260505-own): apply connect_timeout default + retry cap to DatabricksDialect`
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_databricks_dialect.py -v && uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py</automated>
  </verify>
  <done>All tests in `tests/unit/test_databricks_dialect.py` pass (pre-existing 23 + new ~6). Ruff clean. GREEN commit created.</done>
</task>

</tasks>

<verification>
- `uv run pytest tests/unit/test_databricks_dialect.py -v` — all pass (baseline 23 + new)
- `uv run pytest tests/` — no regressions across full suite
- `uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py` — clean
- Code inspection: `sa_create_engine` call site includes `connect_args=merged_connect_args` with both `_socket_timeout` and `_retry_stop_after_attempts_count` keys
</verification>

<success_criteria>
- `DatabricksDialect.create_engine()` with no timeout kwarg → `sa_create_engine` receives `connect_args={"_socket_timeout": 30, "_retry_stop_after_attempts_count": 2}`
- `connection_timeout=N` kwarg overrides the socket timeout default
- Caller-supplied `connect_args` dict merges with dialect defaults, caller wins per-key
- Both kwargs-mode and URL-mode call paths receive identical treatment
- Two atomic commits: RED (failing tests) then GREEN (fix)
- No changes outside `src/db/dialects/databricks.py` + `tests/unit/test_databricks_dialect.py`
</success_criteria>

<output>
After completion, create `.planning/quick/260505-own-apply-connect-timeout-default-retry-cap-/260505-own-SUMMARY.md`
</output>
