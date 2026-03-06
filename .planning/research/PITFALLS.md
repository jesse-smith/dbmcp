# Domain Pitfalls

**Domain:** Concern handling improvements for existing MCP server (dbmcp v1.1)
**Researched:** 2026-03-06
**Confidence:** HIGH (based on direct codebase inspection of all affected modules, 506 tests, 25 broad except blocks)

## Critical Pitfalls

### Pitfall 1: Metrics Module Removal Breaks Import Discovery

**What goes wrong:** Removing `src/metrics.py` seems safe -- grep shows zero imports outside the module itself and its own docstring example. But the module is a 258-line singleton with thread-safe state. The real danger is not direct imports but *dynamic* or *deferred* consumers: notebooks in `examples/`, any `importlib` usage, REPL sessions documented in README, or future code that a developer half-wrote in a branch. More concretely, `pyproject.toml` exposes `dbmcp` as an installable package. If any downstream consumer ever ran `from src.metrics import PerformanceMetrics`, their code breaks silently at import time with no deprecation warning.

**Why it happens:** "No grep hits = no consumers" is the standard heuristic, and it is almost always wrong for public-facing modules in installable packages. The module was designed for use (it has a docstring with `from src.metrics import PerformanceMetrics`), so it may have been used in exploratory sessions, notebooks, or forks even if it was never called from production code.

**Consequences:** ImportError at runtime for any consumer that referenced it. Since MCP servers run as subprocesses, this could manifest as silent startup failure -- the server exits, the MCP client retries, and the user sees "tool unavailable" with no clear cause.

**Prevention:**
1. Before removing, search beyond `src/` and `tests/`: check `examples/`, `notebooks/`, `docs/`, `*.ipynb` files, and any `*.md` files that reference the module.
2. Stage the removal: first deprecate by adding a module-level warning (`warnings.warn("metrics module is deprecated and will be removed", DeprecationWarning, stacklevel=2)`), ship that, then remove in a subsequent commit.
3. Alternatively, if the goal is to just remove dead code quickly, verify the module has no `__init__.py` re-export (check `src/__init__.py`) and no dynamic imports, then remove in one commit with a clear commit message explaining why.

**Detection:** If you remove it and tests pass, you are probably safe. But run `uv run python -c "from src.metrics import PerformanceMetrics"` to confirm the import path is dead before committing.

---

### Pitfall 2: Broad Exception Narrowing Changes Error Messages That Tests Assert On

**What goes wrong:** The codebase has 25 `except Exception` blocks across 4 modules (metadata.py has 11, query.py has 3, connection.py has 1, and each of the 3 MCP tool modules has 3). When you narrow `except Exception as e` to `except (sqlalchemy.exc.OperationalError, pyodbc.Error) as e`, the `type(e).__name__` embedded in error messages changes. Currently tests assert on error message content with patterns like `assert "DML" in query.error_message`, `assert "not found" in result["error_message"].lower()`, and `pytest.raises(ValueError, match="Username and password required")`. Changing which exceptions are caught changes which error messages reach the caller, which breaks these assertions.

**Why it happens:** Error messages are an implicit public API. Tests treat them as stable strings. When you replace `except Exception` with `except OperationalError`, an unexpected `ProgrammingError` that was previously caught now propagates upward, changing both the exception type *and* the error message the test sees. The MCP tool layer catches `Exception` as a last resort and wraps it in `f"Unexpected error: {type(e).__name__}: {str(e)}"` -- so the error message format changes even for the same underlying failure.

**Consequences:** Cascading test failures that look like bugs but are actually just error message format changes. In a 506-test suite, this can produce 20-40 false-positive failures that obscure real regression bugs.

**Prevention:**
1. **Audit error message assertions first.** Before changing any `except` clause, grep for tests that assert on the error message text of that function. There are at least 30 such assertions across the test suite.
2. **Change one module at a time**, run the full test suite, and fix assertion drift before moving to the next module.
3. **Do not change the MCP tool layer's catch-all `except Exception`**. The tool layer MUST remain a last-resort safety net that catches anything and returns a TOON error response. Only narrow the exceptions in the *service layer* (metadata.py, query.py, connection.py). The tool layer should catch specific exceptions first (for specific messages) then fall through to `Exception` for the generic case.
4. **Use exception hierarchies, not exception lists.** Instead of `except (OperationalError, ProgrammingError, InterfaceError)`, catch `sqlalchemy.exc.DBAPIError` which is the common base class for all DBAPI-wrapped errors. This is narrower than `Exception` but broad enough to not miss database errors.

**Detection:** Any test failure where the assertion fails on string content of an error message (not on exception type) is probably this pitfall.

---

### Pitfall 3: Azure AD Token Refresh in Connection Pool Creator Closure

**What goes wrong:** The current `_create_engine` in connection.py creates a closure (`def creator()`) that calls `provider.get_token()` on every new connection. This looks like it handles token refresh -- but it does not. SQLAlchemy's `QueuePool` reuses connections from the pool without calling `creator` again. A connection that was created with a valid token stays in the pool for up to `pool_recycle` seconds (default: 3600). Azure AD tokens expire after 60-90 minutes. If the pool hands out a connection whose token has expired, the query fails with an opaque pyodbc error, not a clear "token expired" message.

**Why it happens:** The `creator` function only runs when a *new* raw connection is created (pool miss or pool exhausted). `pool_pre_ping` validates the connection with a lightweight query *before* returning it, which should catch expired tokens -- but `pool_pre_ping` catches `DisconnectionError`, and an expired Azure AD token may not raise `DisconnectionError`. It may raise `pyodbc.OperationalError` with a SQL Server error code that SQLAlchemy does not recognize as a disconnect event. The connection appears "alive" to the pre-ping but fails on the actual query.

**Consequences:** Intermittent query failures after 60-90 minutes of idle time on Azure AD Integrated connections. Users see `OperationalError: Login failed for user '<token>@<domain>'` and must manually reconnect. This is the worst kind of bug: it works in development (tokens are fresh) and fails in production (long-running MCP server sessions).

**Prevention:**
1. **Set `pool_recycle` to less than the token lifetime.** Azure AD tokens last ~3600 seconds. Set `pool_recycle=1800` (30 minutes) for Azure AD connections so the pool proactively discards connections before tokens expire.
2. **Register a `checkout` event** on the engine that validates the token age. If the connection is older than a threshold, force a disconnect so the pool creates a fresh connection (which calls `creator` and gets a new token).
3. **Cache the token in `AzureTokenProvider` with an expiry timestamp.** The `AccessToken` object returned by `DefaultAzureCredential.get_token()` includes an `expires_on` field. Use it to proactively refresh before expiry.
4. **Do NOT try to swap the token on an existing pyodbc connection.** The `SQL_COPT_SS_ACCESS_TOKEN` attribute is set at connection creation time and cannot be updated on an open connection. The only path is to discard the connection and create a new one.

**Detection:** Integration tests that run for >60 minutes on Azure AD connections (not practical in CI). Instead, write a unit test that mocks token expiry and verifies the pool creates a new connection.

---

### Pitfall 4: Identifier Validation Tightening Breaks Legitimate Column Names

**What goes wrong:** The current `_sanitize_identifier` in query.py uses `re.match(r'^[a-zA-Z0-9_\s]+$', identifier)`, which rejects column names containing hyphens, dots, hash signs (`#`), or non-ASCII characters. SQL Server allows all of these in bracket-delimited identifiers: `[First-Name]`, `[Column#1]`, `[Geburtstag]`. Tightening validation to "validate against metadata" (as the concern says) sounds good, but the metadata query itself needs the identifier to construct the SQL. If validation is too strict, users cannot reference columns that exist in their database.

**Why it happens:** The current regex is already overly restrictive. "Hardening" it further risks making it worse. The correct approach is the opposite direction: validate that the identifier *exists in the database metadata*, not that it matches a character pattern. But metadata-based validation requires a database round-trip, which changes the function signature and call pattern.

**Consequences:** Users get `ValueError: Invalid identifier: First-Name` when trying to sample a table that has a column named `First-Name`. This is a regression in functionality for a "security improvement."

**Prevention:**
1. **Replace character validation with metadata validation.** Query `INFORMATION_SCHEMA.COLUMNS` for the target table and check that the identifier is in the result set. This is authoritative and handles any legal SQL Server identifier.
2. **Keep bracket-quoting as the safety mechanism.** Even if metadata validation is added, always emit `[identifier]` in generated SQL. Bracket-quoting is the SQL Server standard for identifier safety and handles all special characters.
3. **Add test fixtures with adversarial column names:** `First-Name`, `Column#1`, `2024_Revenue`, `OrderID (old)`, Unicode column names. These must pass validation if they exist in metadata.
4. **Do not remove the regex entirely without a replacement.** If metadata validation is not ready, the regex is still better than nothing for preventing SQL injection. But relax it to allow the characters SQL Server actually supports in identifiers.
5. **Beware the circular dependency:** if you validate identifiers against metadata, you need a database connection. `_sanitize_identifier` currently does not take a connection argument. Refactoring it to accept one changes 2 call sites in `get_sample_data`.

**Detection:** Any test or user report where a column name with a hyphen, space, or special character fails to sample/query.

---

### Pitfall 5: Type Handler Registry Conflicts with Existing TOON Pre-Serialization

**What goes wrong:** The codebase has TWO type-conversion pipelines: `_truncate_value` in `query.py` (handles bytes, datetime, date, time, Decimal for query results) and `_pre_serialize` in `serialization.py` (handles datetime, date, StrEnum, Decimal for TOON encoding). Adding a "type handler registry" means introducing a THIRD layer. If the registry runs before `_pre_serialize`, the TOON layer may re-convert already-converted values (e.g., converting an ISO string back to... a string, which is harmless) or miss values the registry did not handle (falling through to `_pre_serialize`'s `TypeError`). If the registry runs after `_pre_serialize`, it never sees the original types.

**Why it happens:** The two existing pipelines evolved independently: `_truncate_value` was built for display purposes (truncating large values), `_pre_serialize` was built for TOON serialization. They handle overlapping types (datetime, Decimal) but with different semantics (truncation vs. format conversion). A registry that tries to unify them must understand both purposes.

**Consequences:** Double conversion (harmless but confusing), missed types (TypeError from `_pre_serialize`), or test failures where the output format of a value changes (e.g., a Decimal that was `float(value)` from `_truncate_value` is now `str(value)` from the registry).

**Prevention:**
1. **Decide on a single conversion point.** The registry should replace `_truncate_value` AND be the authoritative type converter called before `_pre_serialize`. Then `_pre_serialize` becomes a thin safety net, not a full converter.
2. **Map the current type flow end-to-end before designing the registry.** For a query result value, the path is: `pyodbc cursor -> SQLAlchemy Row -> _process_rows/_truncate_value -> dict -> encode_response -> _pre_serialize -> encode`. Document what happens to each type at each stage.
3. **Make the registry additive, not replacing.** Let existing code continue to work. The registry handles *new* types (e.g., `uuid.UUID`, `bytearray`) that currently fall through to `TypeError`. Do not change how existing types (datetime, Decimal) are handled unless there is a specific bug.
4. **Test with real SQL Server types that are currently not handled:** `hierarchyid`, `geography`, `xml`, `sql_variant`. These are the types that motivate a registry. Verify the current behavior (crash? silent null? str?) and define the desired behavior.

**Detection:** Any `TypeError: Cannot serialize type` from `_pre_serialize` after the registry is added means the registry missed a type. Any test asserting on the exact format of a datetime or Decimal value may break if the conversion order changes.

---

## Moderate Pitfalls

### Pitfall 6: Config File Loading Creates a Startup Dependency

**What goes wrong:** Adding a config file (TOML, YAML, or INI) that overrides hardcoded defaults introduces a new failure mode at server startup. If the config file is malformed, missing, or specifies an invalid value, the server may crash before it can respond to any MCP request. Currently, all defaults are hardcoded, so the server always starts. The global `_connection_manager = ConnectionManager()` in `server.py` runs at import time -- if it reads a config file that fails to parse, the entire module fails to import.

**Why it happens:** Config file parsing is typically done at module import time or in `__init__`. Errors at this stage propagate as `ImportError` or `ModuleNotFoundError` when other modules try to import from `server.py`, producing confusing tracebacks that do not mention the config file.

**Prevention:**
1. **Never fail on missing config.** The config file must be optional. If it does not exist, use hardcoded defaults (the current behavior). This is the most critical rule.
2. **Parse config lazily, not at import time.** Load the config file in `main()` or on first `connect()` call, not at module-level. This ensures import-time side effects do not change.
3. **Validate config values with explicit error messages.** If `pool_size` is set to `"banana"`, the error should say `"Invalid config: pool_size must be an integer, got 'banana'"`, not a stack trace from `int("banana")`.
4. **Use TOML** (stdlib `tomllib` in Python 3.11+). Do not add a YAML dependency. TOML is already used for `pyproject.toml`, so the syntax is familiar and requires no new dependency.
5. **Define the config schema in code** (a dataclass or TypedDict) and validate against it. Do not pass raw dict values to constructors.

**Detection:** Server fails to start with an opaque error. MCP client shows "server not responding." Check if a `dbmcp.toml` or similar file exists and is malformed.

---

### Pitfall 7: Stored Procedure Allowlist in Config Creates Security Bypass Risk

**What goes wrong:** The concern list mentions "SP allowlist" in the config file. Currently, `SAFE_PROCEDURES` is a hardcoded `frozenset` of 22 system stored procedures in `validation.py`. Moving this to a config file means a user can add arbitrary procedures to the allowlist, potentially including `xp_cmdshell`, `sp_configure`, or custom procedures that modify data. The "read-only" security guarantee of the MCP server now depends on the correctness of a user-editable file.

**Why it happens:** The impulse is to make the allowlist configurable so users can call their own read-only stored procedures. This is a legitimate need. But the mechanism (config file) provides no validation that the added procedures are actually read-only.

**Prevention:**
1. **Keep the hardcoded system SP list as a non-overridable base.** Config can ADD to the list but never remove from it or replace it entirely.
2. **Explicitly deny dangerous procedures regardless of config.** Maintain a denylist (`xp_cmdshell`, `sp_configure`, `sp_executesql`, `xp_*`) that takes precedence over the config allowlist.
3. **Document the security implications** in the config file itself (as comments) and in the README.
4. **Log every SP execution that was allowed via config** (not via the hardcoded base) at WARNING level, so administrators can audit.

**Detection:** Security review finds `xp_cmdshell` in the config allowlist. Or: a user adds a custom SP that does writes, and the "read-only" MCP server silently executes it.

---

### Pitfall 8: sqlglot Version Pin and Edge Case Fixtures Interact Badly

**What goes wrong:** The concern says "Pin sqlglot version and add edge case test fixtures." Currently, `pyproject.toml` has `sqlglot>=26.0.0,<30.0.0`. The validation module depends heavily on sqlglot's AST node types (`exp.Execute`, `exp.ExecuteSql`, `exp.Command`, `exp.Kill`, `exp.IfBlock`, `exp.WhileBlock`). Between sqlglot 26 and 29, the `exp.Execute` node was added as a distinct type (previously, EXEC was parsed as `exp.Command`). The code handles BOTH cases (lines 127-133 and 219-224 of validation.py). Pinning to a specific version eliminates one code path. But if you write test fixtures against the pinned version's AST behavior, the tests become version-locked: upgrading sqlglot later breaks the fixtures.

**Why it happens:** sqlglot is an actively-developed parser that changes AST shapes between minor versions. Pinning stabilizes behavior but creates upgrade debt. Test fixtures that depend on specific parse tree shapes (e.g., "EXEC sp_help parses to Command" vs "EXEC sp_help parses to Execute") encode version-specific assumptions.

**Prevention:**
1. **Pin to a specific minor version** (e.g., `sqlglot==29.x.y`) not a range. This is correct.
2. **Write test fixtures at the SQL level, not the AST level.** Test that `validate_query("EXEC sp_help")` returns `is_safe=True`, not that sqlglot parses it to `exp.Execute`. The validation function is the public API; the AST is an implementation detail.
3. **Keep the dual-path handling** (Execute vs Command) even after pinning. It costs nothing and makes future upgrades safer.
4. **Add a "sqlglot upgrade" test marker** for fixtures that exercise version-sensitive behavior, so they can be run specifically when evaluating a sqlglot upgrade.

**Detection:** Test failures after `uv lock --upgrade` that mention sqlglot AST types.

---

### Pitfall 9: Increasing Test Coverage Without Increasing Test Quality

**What goes wrong:** The target is 70% coverage minimum for all modules. The easiest way to reach this is to write tests that exercise code paths without meaningful assertions: `test_list_schemas_returns_something()` that just calls the function and asserts `result is not None`. These tests inflate coverage metrics but catch no regressions. Worse, they create maintenance burden (tests that break on refactors but never catch bugs).

**Why it happens:** Coverage targets incentivize breadth over depth. The current 506 tests already cover the happy paths well. Getting to 70% on low-coverage modules (likely `metadata.py` with its 11 `except` blocks, and `connection.py`) means testing error paths, edge cases, and platform-specific branches (SQLite vs MSSQL). These are genuinely hard to test well.

**Prevention:**
1. **Focus on behavioral coverage, not line coverage.** For each uncovered code path, ask: "What bug would this test catch?" If the answer is "none," skip it.
2. **Prioritize testing error recovery paths** (the `except` blocks). These are both low-coverage and high-value: they are where bugs hide because they are rarely exercised in development.
3. **Use parameterized fixtures for the SQL Server vs SQLite branches.** `metadata.py` has dual paths for MSSQL and generic databases. The unit tests use SQLite; integration tests use SQL Server. Both paths need coverage.
4. **Avoid mocking the database for metadata tests.** The metadata module is tightly coupled to SQLAlchemy Inspector, and mocking Inspector produces tests that test the mock, not the module. Use an in-memory SQLite database instead.
5. **Write tests that assert on structure, not exact values.** For example, `assert len(columns) > 0 and all("column_name" in c for c in columns)` rather than `assert columns[0]["column_name"] == "id"`.

**Detection:** Coverage reaches 70% but mutation testing (if applied) shows low mutation kill rate. Or: a real bug is introduced in a "covered" function and no test catches it.

---

### Pitfall 10: Session Cleanup on MCP Disconnect Breaks Connection Reuse

**What goes wrong:** The concern says "Close database connections when MCP session ends." The current `ConnectionManager` stores engines in `_engines` dict, and the `mcp` server is a global singleton. If you add shutdown/disconnect hooks that call `disconnect_all()` when the MCP session ends, you may accidentally trigger this during normal operation: FastMCP may close and reopen connections for protocol-level reasons, or a client may briefly disconnect and reconnect. Eager cleanup destroys connection pools that took time to warm up.

**Why it happens:** "Clean up resources" is a good instinct, but MCP session lifecycle is not well-documented. The boundary between "session ended" and "connection temporarily interrupted" is ambiguous in the MCP protocol.

**Prevention:**
1. **Register cleanup on server shutdown (`atexit`), not on session events.** The `atexit` handler runs when the Python process exits, which is the correct time to dispose engines.
2. **Do not call `disconnect_all()` on MCP protocol-level disconnect events.** Only call it when the server process is terminating.
3. **Test the cleanup path explicitly:** create a connection, trigger cleanup, verify `engine.dispose()` was called. Do not test by actually starting and stopping the MCP server (too fragile).

**Detection:** Users report "Connection not found" errors after brief network interruptions. Or: connection pool metrics show repeated pool warming (many initial connections) instead of steady-state reuse.

---

## Minor Pitfalls

### Pitfall 11: type: ignore Removal Requires Understanding the Monkey-Patching Pattern

**What goes wrong:** The three `# type: ignore` comments in `query.py` (lines 546-548) are on monkey-patched attributes (`query._columns`, `query._rows`, `query._total_rows_available`). These are set on a `Query` dataclass instance but are not declared in the dataclass. Removing the `type: ignore` comments without addressing the underlying pattern just moves the problem: mypy/pyright will flag the lines. The fix is to either add the fields to the `Query` dataclass (with defaults) or use a separate result container.

**Prevention:** Fix the pattern, not the suppression. Define a `QueryResult` dataclass or add optional fields to `Query`. Then the `type: ignore` comments become unnecessary.

---

### Pitfall 12: Ruff Pre-Existing Warning Creates "Zero Warnings" Confusion

**What goes wrong:** MEMORY.md notes a pre-existing ruff warning in `src/metrics.py` (Generator import from `typing` instead of `collections.abc`). If the goal is "zero warnings before commit," this existing warning must be fixed first or explicitly excluded. Otherwise, every feature branch starts with a failing lint gate.

**Prevention:** Fix the ruff warning as part of the metrics module removal. If the module is kept, fix the import. If removed, the warning goes away with it.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Dead code removal (metrics.py) | Hidden consumers (Pitfall 1), ruff warning (Pitfall 12) | Search all file types, not just `.py`; remove module cleanly |
| Exception narrowing (25 blocks) | Error message assertion drift (Pitfall 2) | Audit test assertions first; change one module at a time |
| Azure AD token refresh | Token expiry in pooled connections (Pitfall 3) | Set pool_recycle < token lifetime; cache token expiry timestamp |
| Identifier validation hardening | Over-restrictive validation breaks legit queries (Pitfall 4) | Use metadata validation, not regex; test with special-char columns |
| Type handler registry | Triple-conversion pipeline conflict (Pitfall 5) | Map existing type flow first; make registry additive |
| Config file support | Startup failure on bad config (Pitfall 6), SP allowlist bypass (Pitfall 7) | Config is optional; hardcoded SPs are non-overridable base |
| sqlglot pin + edge cases | Version-locked test fixtures (Pitfall 8) | Test at SQL level, not AST level |
| Test coverage to 70% | Hollow tests that inflate metrics (Pitfall 9) | Focus on behavioral coverage of error paths |
| Session cleanup | Premature connection disposal (Pitfall 10) | Use atexit, not session events |
| type: ignore fixes | Monkey-patching pattern needs redesign (Pitfall 11) | Create proper result container type |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Exception narrowing + TOON error responses | Changing which exceptions are caught changes the `type(e).__name__` in TOON error strings; tests assert on these strings | Keep tool-layer catch-all; narrow only service-layer exceptions; update test assertions |
| Config file + ConnectionManager | Loading config at import time causes `server.py` to crash if config is malformed | Load config lazily in `main()` or first `connect()` call |
| Type handler registry + serialization.py | Registry converts datetime to string; `_pre_serialize` tries to convert it again (no-op but wasteful) | Make `_pre_serialize` idempotent for already-converted types; or make registry the sole converter |
| Azure AD token refresh + pool_pre_ping | Pre-ping may not detect expired token (error code not recognized as disconnect) | Set pool_recycle shorter than token lifetime as primary defense; pre-ping is secondary |
| Identifier validation + get_sample_data columns param | Metadata validation needs a DB connection; `_sanitize_identifier` currently is a pure function | Refactor to accept connection/metadata, or validate at the caller level before calling _sanitize |

## Sources

- Direct codebase inspection: `src/db/connection.py`, `src/db/query.py`, `src/db/validation.py`, `src/db/metadata.py`, `src/db/azure_auth.py`, `src/serialization.py`, `src/metrics.py`, `src/mcp_server/server.py`, `src/mcp_server/schema_tools.py`, `src/mcp_server/query_tools.py`, `src/mcp_server/analysis_tools.py`
- Test suite inspection: 506 tests, 30+ error message assertions, `pytest.raises(match=...)` patterns
- Azure AD token behavior: azure-identity DefaultAzureCredential returns `AccessToken` with `expires_on` field (HIGH confidence, documented in azure-identity SDK)
- SQLAlchemy pool behavior: `pool_pre_ping` uses `is_disconnect()` check which may not cover all Azure AD token expiry error codes (HIGH confidence, SQLAlchemy docs)
- sqlglot AST changes: Execute node added in sqlglot ~29.x, validation.py handles both old and new paths (HIGH confidence, codebase evidence)
- Python 3.11 stdlib `tomllib`: available for TOML parsing without new dependencies (HIGH confidence)

---
*Pitfalls research for: dbmcp v1.1 Concern Handling improvements*
*Researched: 2026-03-06*
