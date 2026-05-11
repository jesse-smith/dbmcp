# Phase 14: Connect-time hardening (Databricks) - Research

**Researched:** 2026-05-11
**Domain:** Databricks connection identity (catalog handling, connect-time validation, regression test closure)
**Confidence:** HIGH — all decisions locked in CONTEXT.md; research is implementation-path only. Code paths verified in-repo.

## Summary

Phase 14 closes the catalog-handling bug class on the Databricks dialect. Three narrow edits to production code plus four tests:

1. `DatabricksDialect`: remove two `"main"` defaults (lines 149, 239); add a `ValueError` guard in `create_engine`; add a new `list_catalogs(engine)` method.
2. `ConnectionManager`: add a `_require_databricks_catalog` helper that sits in the two connect-time IO paths (`connect_with_url`, `_connect_databricks_from_config`), catches the dialect's `ValueError`, runs `SHOW CATALOGS` via a bare engine, and re-raises as `ConnectionError` with a formatted message.
3. `MetadataService`: delete `_list_databricks_catalogs`, delete the `try/except SQLAlchemyError` fallback in `list_schemas`, rename `_databricks_default_catalog` → `_engine_catalog`, update `list_schemas` docstring.
4. Tests: IDENT-01 (catalog-required error surfaces `SHOW CATALOGS` output with chained cause), IDENT-02 (regression — `list_schemas` never calls `SHOW CATALOGS`), TEST-01 (env-var resolution for catalog/schema), TEST-02 (`SQLAlchemyError` → `ConnectionError` with host in message).

All 17 decisions (D-01 through D-17) are locked. No alternative paths need research.

**Primary recommendation:** Implement in the order dialect → connect-layer helper → metadata cleanup → tests, committing at each boundary. The engine-spy pattern in `tests/unit/test_connect_with_config_databricks.py` (`_make_engine_spy`, `monkeypatch.setattr(DatabricksDialect, "create_engine", ...)`) is the template for every new test.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Catalog-missing detection:**
- **D-01:** The catalog-required check lives in `DatabricksDialect.create_engine`. One guard covers both URL mode and kwargs mode. Missing OR empty-string catalog both count as missing.
- **D-02:** Remove the `catalog: str = kwargs.get("catalog", "main")` default at `src/db/dialects/databricks.py:239`. Also remove `query.get("catalog", "main")` in `_kwargs_from_url` at line 149.
- **D-03:** `create_engine` raises plain `ValueError("Databricks catalog is required")` on missing/empty catalog. Keeps `create_engine` IO-free.

**Error shape for IDENT-01 (enriched at connect layer):**
- **D-04:** Rich error constructed at connect layer. `connect_with_url` and `connect_with_config` share a `_require_databricks_catalog(...)` helper that catches `ValueError`, builds a bare engine without catalog, runs `SHOW CATALOGS`, re-raises as `ConnectionError`.
- **D-05:** Error body format: first 20 catalogs + `(N more)` suffix when truncated. Template:
  > `Databricks connection requires a catalog. Accessible catalogs: main, hive_metastore, samples, ... (and 4 more). Pass one via ?catalog= in the URL or catalog= in the config.`
- **D-06:** If `SHOW CATALOGS` itself fails, chain via `raise ConnectionError(...) from exc`. Message names both problems.
- **D-07:** Connect-layer error class: custom `ConnectionError` at `src/db/connection.py:65`. Dialect-level `ValueError` stays as last-line defense.

**SHOW CATALOGS helper placement:**
- **D-08:** `DatabricksDialect.list_catalogs(engine) -> list[str]` — dialect-owned.

**Scope of fallback removal:**
- **D-09:** Delete `_list_databricks_catalogs` at `src/db/metadata.py:164-190`.
- **D-10:** Delete `try/except SQLAlchemyError` wrapper at `src/db/metadata.py:107-115`.
- **D-11:** Rename `_databricks_default_catalog` → `_engine_catalog`. Strip `"main"` fallbacks; body becomes `return self.engine.url.query["catalog"]`. Let `KeyError` propagate.
- **D-12:** Update `list_schemas` docstring at `src/db/metadata.py:79-94`. State post-IDENT-01 invariant.
- **D-13:** Keep `list_schemas(catalog=...)` as optional parameter.

**Regression tests:**
- **D-14:** IDENT-01 test — catalog-less URL raises `ConnectionError`; message contains `SHOW CATALOGS` output; chained `__cause__`; when `SHOW CATALOGS` patched to raise, outer error names both problems.
- **D-15:** IDENT-02 regression — spy on engine/dialect during `list_schemas`; assert no `SHOW CATALOGS` query ever issued.
- **D-16:** TEST-01 — env var resolution for `catalog="${DBX_CATALOG}"` and `schema_name="${DBX_SCHEMA}"`.
- **D-17:** TEST-02 — patched `create_engine` raises `SQLAlchemyError`; assert `ConnectionError` raised; host in message.

### Claude's Discretion
- Exact test file naming (one file vs two).
- Exact wording of user-facing error messages (D-05 gives template; small tweaks fine).
- Structural placement of `_require_databricks_catalog` (module function, private method on `ConnectionManager`, or dialect helper) — flexible as long as D-04/D-06 behavior holds.

### Deferred Ideas (OUT OF SCOPE)
- No `ConfigurationError` type introduction — tech-debt follow-up.
- No broader "default catalog" MSSQL-vocabulary audit — future cleanup.
- `DISC-01` (`list_catalogs`/`list_databases` tool) — will reuse the helper we build here, but lives in a future milestone.
- Phase 15 identifier-resolver refactor (IDENT-03 through IDENT-07) — depends on Phase 14.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-01 | `connect_database` rejects Databricks without catalog; error lists accessible catalogs | D-01/D-04/D-05/D-06 specify implementation path. `SHOW CATALOGS` shape verified below. |
| IDENT-02 | `list_schemas` no longer returns catalog names as schemas | D-09/D-10/D-11 specify deletion targets. Pre-bug failure mode identified at `src/db/metadata.py:107-115`. |
| TEST-01 | `test_env_var_substitution_for_catalog_and_schema` | D-16 specifies assertion shape. Env-var resolution path traced below (`resolve_env_vars` at `src/config.py:119`, applied in `_connect_databricks_from_config` at `src/db/connection.py:496-500`). |
| TEST-02 | `test_sqlalchemy_error_wrapped_as_connection_error` | D-17 specifies shape. Wrapping pattern exists at `src/db/connection.py:527-535`; safe-url-with-host form used at lines 363-365, 382-384. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Catalog presence validation | Dialect (`DatabricksDialect.create_engine`) | — | Pure validation; no IO. Matches existing `host`/`http_path` pattern at lines 233-236. |
| `SHOW CATALOGS` SQL execution | Dialect (`DatabricksDialect.list_catalogs`) | — | Dialect-specific SQL lives with dialect. D-08. |
| Bare-engine construction for catalog probe | Dialect (via `create_engine` with placeholder catalog OR a dedicated bare-engine method) | Connect layer | Connect layer decides when to probe; dialect knows how to build. |
| Rich error message assembly | Connect layer (`ConnectionManager._require_databricks_catalog`) | — | IO is here; wrapping pattern already lives here. D-04. |
| Env-var resolution before engine creation | Connect layer (`_connect_databricks_from_config`) | Config layer (`resolve_env_vars`) | Already in place at `connection.py:496-500`; TEST-01 locks. |
| Catalog readback for `list_schemas` | Metadata service (`_engine_catalog`) | Dialect (URL parser put it there) | Post-IDENT-01, invariant is "catalog is always in engine.url.query". |

## Standard Stack

No new dependencies. All tools in place from earlier phases.

### Core (already present)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp[cli]` | >=1.0.0 | MCP server framework | Core project runtime |
| `sqlalchemy` | >=2.0.0 | Engine + URL parsing (`make_url`) | `make_url` is used for `render_as_string(hide_password=True)` safe-URL pattern |
| `databricks-sqlalchemy` | (installed via `databricks.sql`) | Databricks dialect driver | Already integrated; `SHOW CATALOGS` works through the existing `text()` execute path |
| `pytest` | 7.0.0+ | Test runner | Existing `_make_engine_spy` pattern already in use |
| `pytest-asyncio` | 0.21.0+ | Async MCP tool testing | Not relevant for Phase 14 (connect-layer code is sync) |

**Installation:** None needed — all packages in `pyproject.toml`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Running `SHOW CATALOGS` via a bare engine after `ValueError` | Parse `SHOW CATALOGS` from the failing engine's own connection | Rejected by D-04: dialect stays IO-free. The connect layer builds a bare engine itself. |
| `ConfigurationError` type | Plain `ValueError` | Rejected — D-07 reuses existing `ConnectionError` class; dedicated config-error type is deferred tech debt. |

## `SHOW CATALOGS` — command shape and failure modes

[CITED: Databricks SQL reference — `SHOW CATALOGS` https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-show-catalogs.html]

**Syntax:** `SHOW CATALOGS [LIKE pattern]`. No parameters needed for our case.

**Result shape:** Single-column result set; column name is `catalog`. Each row is a string. Iterating `row[0]` is the canonical extraction pattern (same pattern used in the existing `_list_databricks_catalogs` at `src/db/metadata.py:174-175`, which we're deleting but whose iteration shape is correct).

**Permissions model:**
- Unity Catalog: user sees only catalogs they have USE CATALOG on (plus `hive_metastore`, `samples`, `system` if granted).
- Non-UC workspaces: typically `hive_metastore` and `samples` are visible.
- `SHOW CATALOGS` itself does not require elevated permissions — it reports what the principal can see. Empty result is possible if the workspace is locked down.

**Failure modes to handle (for D-06):**
1. **Connectivity failure on bare-engine probe** — `SQLAlchemyError` (likely `OperationalError`). Most common on bad `host`/`http_path`/`token`.
2. **Auth failure** — surfaces as `DatabaseError` / `ProgrammingError`. Token expired or invalid.
3. **Empty catalog list** — valid state (principal has no catalog grants). Not an exception, but the error message should handle it gracefully ("Accessible catalogs: (none).").
4. **Import-time failure** — `databricks-sqlalchemy` not installed. The dialect already guards this at `src/db/dialects/databricks.py:221-225` with a helpful `ImportError`. Our new path does not need to re-handle.

**Implementation note for `list_catalogs`:** Use `conn.execute(text("SHOW CATALOGS")).fetchall()` followed by `[row[0] for row in rows]`. Let `SQLAlchemyError` propagate — the connect-layer helper catches and wraps.

## Safe-URL / host-string formatting (TEST-02 relevance)

Verified in code at `src/db/connection.py`:

- **Lines 363-365** (`connect_with_url`): `safe_url = parsed_url.render_as_string(hide_password=True)` → error message `f"Could not connect to {safe_url}: {str(e)}"`.
- **Lines 382-384** (`connect_with_url` post-`_register_engine`): same pattern.
- **Lines 527-535** (`_connect_databricks_from_config`): different shape — error string is `f"Could not connect to databricks://{host}: {str(e)}"`. **This is the one TEST-02 targets.** The `host` variable comes from `resolve_env_vars(config.host)` at line 496.

**TEST-02 assertion pattern:**
```python
with pytest.raises(ConnectionError) as exc_info:
    manager.connect_with_config(cfg, DatabricksDialect())
assert "dbc-test.cloud.databricks.com" in str(exc_info.value)  # host appears in message
```

No new `safe_url` helper is needed. The Databricks branch already embeds `host` literally (no token in it — token is URL-encoded only in the canonical URL at line 511, which is used for `connection_id` only). Continue this pattern when composing IDENT-01 messages.

## Engine-spy pattern — template for all new tests

Verified in `tests/unit/test_connect_with_config_databricks.py`:

```python
def _make_engine_spy():
    engine = MagicMock(name="Engine")
    conn = MagicMock(name="SQLAConnection")
    conn.execute.return_value = MagicMock(fetchone=lambda: (1,))
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = ctx
    return engine
```

**Interception points used:**
1. `monkeypatch.setattr(DatabricksDialect, "create_engine", spy_create_engine)` — captures kwargs, returns engine spy. Preserves the real dispatch path (Bug B coverage).
2. `monkeypatch.setattr(ConnectionManager, "_test_connection", lambda self, engine, start_time, dialect_name: None)` — neutralizes `SELECT 1` probe.

**Adapting the spy for IDENT-01 / IDENT-02:**

For IDENT-01 (D-14), we need `SHOW CATALOGS` to return a list. Extend `_make_engine_spy` (or add a sibling factory):
```python
def _make_engine_spy_with_catalogs(catalog_names):
    engine = _make_engine_spy()
    conn = engine.connect.return_value.__enter__.return_value
    # conn.execute(text("SHOW CATALOGS")).fetchall() → [(name,), ...]
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [(n,) for n in catalog_names]
    # _test_connection still calls execute("SELECT 1") — first call returns fetchone
    # list_catalogs path calls execute("SHOW CATALOGS") — returns fetchall
    conn.execute.side_effect = lambda stmt: (
        result_mock if "CATALOG" in str(stmt).upper() else MagicMock(fetchone=lambda: (1,))
    )
    return engine
```

For IDENT-02 (D-15), the assertion is *negative*: the spy records every `conn.execute` call and the test asserts no `SHOW CATALOGS` was issued.
```python
execute_calls = []
conn.execute.side_effect = lambda stmt, *a, **kw: (execute_calls.append(str(stmt)), MagicMock(fetchall=list))[1]
# ... exercise list_schemas ...
assert not any("SHOW CATALOGS" in call.upper() for call in execute_calls)
```

**File placement discretion (D-14):** Adding to the existing `tests/unit/test_connect_with_config_databricks.py` keeps the spy factory local (DRY). A new file `test_connect_databricks_catalog_required.py` is defensible if the count of new tests exceeds ~4 or fixtures grow. Recommendation: **one file for Phase 14** (it's still a small test count). If the planner later adds many tests, split.

## Env-var resolution order (TEST-01 relevance)

Traced in code:

1. `src/config.py:119` — `resolve_env_vars(value)` walks `${VAR}` patterns and replaces with `os.environ.get(name)`. Raises `ValueError` if unset.
2. `src/db/connection.py:496-500` — called per-field in `_connect_databricks_from_config`:
   ```python
   host = resolve_env_vars(config.host) if config.host else ""
   http_path = resolve_env_vars(config.http_path) if config.http_path else ""
   token = resolve_env_vars(config.token) if config.token else ""
   catalog = resolve_env_vars(config.catalog) if config.catalog else "main"
   schema = resolve_env_vars(config.schema_name) if config.schema_name else "default"
   ```
3. Resolved values are passed as kwargs to `dialect.create_engine(...)` at line 520-526.

**TEST-01 spy point:** Intercept `DatabricksDialect.create_engine` (as existing test does), assert `captured_kwargs["catalog"]` and `captured_kwargs["schema"]` are the resolved values (e.g., `"my_resolved_catalog"`), not `"${DBX_CATALOG}"` literals.

**Open detail for the planner:** Line 499 currently has the fallback `else "main"` — after D-02, this default must also be removed (the `"main"` fallback is exactly the IDENT-01 bug class). D-02 names lines 149 and 239 in `databricks.py` but the same logic lives at **`connection.py:499`** too. **This is a third deletion point CONTEXT.md does not explicitly call out.** Planner must confirm with D-02's spirit: no hidden `"main"` defaults anywhere on the Databricks connect path. Recommend: `catalog = resolve_env_vars(config.catalog) if config.catalog else ""` (empty triggers dialect `ValueError`, which the `_require_databricks_catalog` helper then enriches). Same for `schema` default, though `schema_name` defaulting to `"default"` is Databricks-meaningful and does not have the same silent-wrong-data bug class.

[ASSUMED] The `"main"` fallback at `connection.py:499` is in-scope for Phase 14. CONTEXT.md D-02 calls out lines 149 and 239 of `databricks.py` only. Planner should confirm in discuss-phase whether this line is covered implicitly or if it needs a separate decision.

## Pre-IDENT-01 failure mode (the bug IDENT-02 regression test locks)

Verified at `src/db/metadata.py:107-115`:

```python
default_catalog = self._databricks_default_catalog()
try:
    result = self._list_schemas_databricks(connection_id, default_catalog)
except SQLAlchemyError as exc:
    logger.info(...)
    result = self._list_databricks_catalogs(connection_id)   # ← the bug
```

**What went wrong:** When the engine's configured default catalog (often silently `"main"` due to the `"main"` fallback) didn't exist on the workspace, `SHOW SCHEMAS IN \`main\`` failed, and the `except` branch swapped in `SHOW CATALOGS`. The returned list looks like schemas to the caller (each `Schema` object has the catalog name in `schema_name`), but they are catalogs. Downstream tools then got confused. IDENT-02 regression asserts this path is gone.

**The lock:** D-15's spy asserts `SHOW CATALOGS` is *never* issued during `list_schemas` on a Databricks connection. Once the `except` block and `_list_databricks_catalogs` method are deleted (D-09, D-10), the only remaining `SHOW CATALOGS` callsite is `DatabricksDialect.list_catalogs`, which `list_schemas` does not call.

## Runtime State Inventory

Not applicable. Phase 14 is a code-edit phase only — no rename, migration, or external service state changes. No stored data, live service config, OS-registered state, secrets, or build artifacts embed the strings being modified.

## Common Pitfalls

### Pitfall 1: `_kwargs_from_url` line 149 still has `"main"` default
**What goes wrong:** URL mode (`sqlalchemy_url=databricks://...`) without `?catalog=` silently falls back to `"main"` — same bug as kwargs mode.
**Why it happens:** D-02 names this line explicitly but it's easy to miss during implementation because it lives in a helper, not in `create_engine` proper.
**How to avoid:** Change line 149 to `catalog = query.get("catalog", "")` (empty string). Then the downstream check in `create_engine` (D-01 guard) catches it.
**Warning signs:** TEST-01 passes but IDENT-01 URL-mode test fails — indicates one of the two defaults is still present.

### Pitfall 2: `_require_databricks_catalog` running `SHOW CATALOGS` on a dead engine
**What goes wrong:** If `host`/`http_path`/`token` are bad, the bare-engine probe for `SHOW CATALOGS` fails with `OperationalError`. Message should name both problems (D-06).
**Why it happens:** Naive implementations re-raise only the catalog-required error, hiding the probe failure.
**How to avoid:** Wrap the `list_catalogs(bare_engine)` call in its own `try/except SQLAlchemyError`. On exception, compose a message like: `"Databricks connection requires a catalog, and SHOW CATALOGS failed: {exc}. Pass ?catalog= explicitly."` — chained via `from exc` so `__cause__` still carries the probe error.
**Warning signs:** D-14's test case "when SHOW CATALOGS is patched to raise" fails or produces a message naming only one problem.

### Pitfall 3: The bare-engine probe needs a placeholder catalog
**What goes wrong:** After D-02, `create_engine` rejects empty catalog with `ValueError`. So the probe engine also fails to construct.
**Why it happens:** The strictness applies everywhere.
**How to avoid:** Two options: (a) probe by passing a placeholder catalog (e.g., `"system"` or `"samples"` — both typically exist on Databricks workspaces) just to construct a connectable engine; (b) add a dialect-private `_create_engine_for_listing(...)` that skips the catalog guard. Option (a) is simpler and stays within the public API. Planner picks; recommend (a) with a constant `_CATALOG_PROBE_PLACEHOLDER = "system"` on the dialect.
**Warning signs:** `ValueError: Databricks catalog is required` bubbles up from inside `_require_databricks_catalog`'s own engine construction.

### Pitfall 4: `_engine_catalog` rename breaks other callers
**What goes wrong:** If other files reference `_databricks_default_catalog` by name, the rename breaks them.
**How to avoid:** Grep before renaming: `rg "_databricks_default_catalog" src/ tests/` — confirm single-caller-only before renaming.
**Warning signs:** Tests or modules not in the phase scope fail with `AttributeError`.

### Pitfall 5: Test for D-14 (c) — chained `__cause__` assertion
**What goes wrong:** `assert exc.__cause__` passes when any exception is chained, but we need the specific `ValueError` from the dialect.
**How to avoid:** Assert `isinstance(exc.__cause__, ValueError)` and that `"catalog" in str(exc.__cause__).lower()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL password hiding | Custom regex stripping | `parsed_url.render_as_string(hide_password=True)` (existing pattern at `connection.py:363`) | SQLAlchemy's implementation already handles edge cases |
| Env var substitution | New `${VAR}` parser | Existing `resolve_env_vars` at `src/config.py:119` | Already consumed at `connection.py:496-500` |
| Exception chaining | Manual `.args[0] = ...` manipulation | `raise ConnectionError(msg) from exc` | Python standard; `.__cause__` flows naturally |
| Engine spy / `SELECT 1` neutralization | New fixture from scratch | Extend `_make_engine_spy` in `tests/unit/test_connect_with_config_databricks.py` | Pattern is proven; other tests already rely on it |

## Code Examples

### D-01 / D-03: Catalog guard in `create_engine`
```python
# src/db/dialects/databricks.py (after existing host/http_path KeyError guard at ~line 236)
# Replace line 239:
catalog: str = kwargs.get("catalog", "")  # was: kwargs.get("catalog", "main")
if not catalog:
    raise ValueError("Databricks catalog is required")
schema: str = kwargs.get("schema", "default")
```

### D-02: URL-mode catalog default removal
```python
# src/db/dialects/databricks.py line 149:
catalog = query.get("catalog", "")  # was: query.get("catalog", "main")
# Downstream create_engine guard will catch empty.
```

### D-08: `list_catalogs` dialect method
```python
# src/db/dialects/databricks.py — new method on DatabricksDialect
def list_catalogs(self, engine: Engine) -> list[str]:
    """Return catalog names visible to the connected principal via SHOW CATALOGS.

    Used by the connect-time helper that enriches the catalog-required error,
    and (future) by DISC-01's list_catalogs tool.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("SHOW CATALOGS")).fetchall()
    return [row[0] for row in rows]
```

### D-04 / D-05 / D-06: Connect-layer helper
```python
# src/db/connection.py — new helper used by both URL and config paths
def _require_databricks_catalog(
    dialect: DatabricksDialect,
    *,
    host: str,
    http_path: str,
    token: str,
    schema: str,
    orig_value_error: ValueError,
) -> "Never":
    """Raise a ConnectionError enriched with accessible catalogs.

    Called when DatabricksDialect.create_engine raised ValueError because
    catalog was missing. Builds a bare engine with a probe-only catalog,
    runs SHOW CATALOGS, formats the message, and raises ConnectionError
    with the original ValueError chained.
    """
    hint = "Pass one via ?catalog= in the URL or catalog= in the config."
    try:
        probe_engine = dialect.create_engine(
            host=host,
            http_path=http_path,
            token=token,
            catalog="system",  # placeholder — any connectable catalog
            schema=schema or "default",
        )
        catalogs = dialect.list_catalogs(probe_engine)
        probe_engine.dispose()
    except SQLAlchemyError as probe_exc:
        raise ConnectionError(
            f"Databricks connection requires a catalog, and "
            f"SHOW CATALOGS failed ({type(probe_exc).__name__}: {probe_exc}). "
            f"{hint}"
        ) from orig_value_error
    except Exception as probe_exc:
        raise ConnectionError(
            f"Databricks connection requires a catalog, and probing "
            f"SHOW CATALOGS failed ({type(probe_exc).__name__}: {probe_exc}). "
            f"{hint}"
        ) from orig_value_error

    truncated = catalogs[:20]
    suffix = f" (and {len(catalogs) - 20} more)" if len(catalogs) > 20 else ""
    listing = ", ".join(truncated) if truncated else "(none)"
    raise ConnectionError(
        f"Databricks connection requires a catalog. "
        f"Accessible catalogs: {listing}{suffix}. {hint}"
    ) from orig_value_error
```

### D-09 / D-10 / D-11 / D-12: Metadata cleanup
```python
# src/db/metadata.py — list_schemas Databricks branch becomes single-path:
if self._dialect and self._dialect.name == "databricks":
    effective_catalog = catalog or self._engine_catalog()
    result = self._list_schemas_databricks(connection_id, effective_catalog)

# _engine_catalog replaces _databricks_default_catalog:
def _engine_catalog(self) -> str:
    """Return the catalog the engine was built with (IDENT-01 invariant)."""
    return self.engine.url.query["catalog"]

# _list_databricks_catalogs: DELETED.
```

### D-14: IDENT-01 test skeleton
```python
def test_connect_databricks_catalog_required_lists_accessible_catalogs(monkeypatch):
    """Catalog-less URL raises ConnectionError containing SHOW CATALOGS output."""
    monkeypatch.setattr(
        ConnectionManager, "_test_connection",
        lambda self, engine, start_time, dialect_name: None,
    )
    # Spy: create_engine raises ValueError on missing catalog (real behavior),
    # but the probe engine build succeeds and SHOW CATALOGS returns a list.
    real_create_engine = DatabricksDialect.create_engine

    def spy(self, **kw):
        if not kw.get("catalog"):
            raise ValueError("Databricks catalog is required")
        return _make_engine_spy_with_catalogs(["main", "hive_metastore", "samples"])

    monkeypatch.setattr(DatabricksDialect, "create_engine", spy)

    cfg = DatabricksConnectionConfig(
        host="example.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/x",
        token="t",
        catalog="",  # missing on purpose
        schema_name="default",
    )
    with pytest.raises(ConnectionError) as exc_info:
        ConnectionManager().connect_with_config(cfg, DatabricksDialect())

    msg = str(exc_info.value)
    assert "catalog" in msg.lower()
    assert "main" in msg and "hive_metastore" in msg and "samples" in msg
    assert isinstance(exc_info.value.__cause__, ValueError)
```

### D-17: TEST-02 skeleton
```python
def test_sqlalchemy_error_wrapped_as_connection_error(monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    def boom(self, **kw):
        raise SQLAlchemyError("boom")
    monkeypatch.setattr(DatabricksDialect, "create_engine", boom)

    cfg = DatabricksConnectionConfig(
        host="dbc-test.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/abc",
        token="t",
        catalog="main",
        schema_name="default",
    )
    with pytest.raises(ConnectionError) as exc_info:
        ConnectionManager().connect_with_config(cfg, DatabricksDialect())
    assert "dbc-test.cloud.databricks.com" in str(exc_info.value)
```

## Project Constraints (from CLAUDE.md)

- **`uv run` only** for Python and Python tooling. Test invocation: `uv run pytest tests/unit/test_connect_with_config_databricks.py -v`.
- **Coverage floor: 85%** (raised in Phase 13). Deletions in `metadata.py` (D-09, D-10, D-11 body) will *increase* coverage by removing untested-or-barely-tested branches. New tests in Phase 14 add coverage on `connection.py` and `databricks.py`.
- **No Pandas**; not relevant here.
- **Sqlglot dependency bumps require explicit test validation** — not relevant (no sqlglot changes).
- Pre-existing `ruff` warning in `src/metrics.py` — unrelated to Phase 14; do not touch unless adjacent.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Silent `catalog="main"` fallback on Databricks | Explicit catalog required at connect time, rich error on absence | Phase 14 (this phase) | Breaking change for any existing catalog-less Databricks config. Documented in REQUIREMENTS.md as intentional. |
| `list_schemas` returns catalog names when default catalog inaccessible | `list_schemas` assumes engine-bound catalog is valid; no fallback | Phase 14 (this phase) | Removes the "schemas are actually catalogs" silent data-corruption class. |
| Direct `SQLAlchemyError → ConnectionError` wrap only | Catalog-missing `ValueError` also flows into `ConnectionError` via shared helper | Phase 14 (this phase) | Unified connect-time error surface. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `"main"` fallback at `src/db/connection.py:499` (in `_connect_databricks_from_config`) is in-scope for Phase 14 under D-02's spirit. | Env-var resolution order | If out of scope, the catalog-required guard is bypassed when `config.catalog` is unset — IDENT-01 incomplete for named-config path. Planner should confirm explicitly. |
| A2 | Placeholder catalog `"system"` (or `"samples"`) is universally connectable on Databricks workspaces for the probe path. | Pitfall 3 | If neither is accessible, the probe fails and we fall into the "SHOW CATALOGS itself failed" branch (D-06) — which is still acceptable. The assumption is about the happy path, not correctness. Confidence: MEDIUM. Could alternatively add a dialect private method that constructs an engine without the catalog guard. |
| A3 | `SHOW CATALOGS` result shape is `(catalog_name,)` tuples — a single column accessed as `row[0]`. | `SHOW CATALOGS` command shape | Verified by reading the existing `_list_databricks_catalogs` code at `metadata.py:174` which uses `row[0]`. Confidence: HIGH. |
| A4 | The existing `databricks-sqlalchemy` install handles `SHOW CATALOGS` via the generic `conn.execute(text(...))` path the way `SHOW SCHEMAS IN` does today. | `list_catalogs` implementation | If the driver requires a different pattern, the probe fails but the outer `try/except SQLAlchemyError` in `_require_databricks_catalog` catches it — degrades gracefully. Confidence: HIGH (pattern already used elsewhere in the codebase). |

## Open Questions

1. **Is `connection.py:499`'s `"main"` fallback a separate deletion target?**
   - What we know: D-02 names `databricks.py:149,239` explicitly but not `connection.py:499`.
   - What's unclear: Whether the discuss-phase author considered this line or missed it.
   - Recommendation: Planner surfaces as a planning-time question, treats as in-scope absent a counter-decision.

2. **Placeholder catalog for probe engine — dialect constant or plain string?**
   - What we know: Needs to be connectable on most workspaces; `"system"` and `"samples"` are candidates.
   - What's unclear: Whether the planner/executor wants this abstracted.
   - Recommendation: Inline `"system"` with a comment for now; no abstraction until there's a second caller.

3. **Test file split — one vs two?**
   - What we know: D-14 leaves discretion.
   - Recommendation: Keep in `test_connect_with_config_databricks.py` (total new test count ≈ 4).

## Environment Availability

Skipped — Phase 14 is pure code + unit tests. No external services, runtimes, or databases needed. All unit tests mock the engine boundary; no live Databricks connection is required. The Live Test Database in MEMORY.md (`stemsoftclinictest`) is MSSQL — irrelevant here.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0.0+ (existing) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_connect_with_config_databricks.py -v` |
| Full suite command | `uv run pytest tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDENT-01 | Catalog-less Databricks connect raises `ConnectionError` with SHOW CATALOGS output, chained `ValueError`, host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_lists_accessible_catalogs -x` | ✅ (extend existing file) |
| IDENT-01 | When SHOW CATALOGS itself fails, outer error names both problems | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_surfaces_show_catalogs_failure -x` | ✅ (new case) |
| IDENT-01 | URL mode (sqlalchemy_url without ?catalog=) also rejected | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_with_url_databricks_requires_catalog -x` | ✅ (new case) |
| IDENT-02 | `list_schemas` on Databricks never issues SHOW CATALOGS | unit | `uv run pytest tests/unit/test_metadata.py::test_list_schemas_databricks_does_not_fall_back_to_show_catalogs -x` | ❌ Wave 0 — new test in `test_metadata.py` |
| TEST-01 | Env var placeholders in `catalog`/`schema_name` resolve before dialect receives kwargs | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_env_var_substitution_for_catalog_and_schema -x` | ✅ (extend existing file) |
| TEST-02 | SQLAlchemyError from create_engine surfaces as ConnectionError with host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_sqlalchemy_error_wrapped_as_connection_error -x` | ✅ (extend existing file) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_connect_with_config_databricks.py tests/unit/test_metadata.py -x`
- **Per wave merge:** `uv run pytest tests/ -m "not integration"` (fast unit suite)
- **Phase gate:** `uv run pytest tests/` (full suite green, 85% coverage floor maintained) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_metadata.py` — confirm file exists; add the IDENT-02 test case. If missing or coverage is thin for `list_schemas` Databricks branch, add fixtures for a Databricks-bound `MetadataService` (inject a `DatabricksDialect` via the `dialect=` kwarg, plus an engine-spy with `engine.url.query = {"catalog": "my_cat"}`).
- [ ] Shared `_make_engine_spy_with_catalogs(catalog_names)` factory — either co-located in `test_connect_with_config_databricks.py` alongside the existing `_make_engine_spy`, or promoted to `tests/unit/conftest.py` if reused.
- [ ] No framework install needed — pytest + monkeypatch already in use.

### Validation Dimensions
1. **Happy path (TEST-01):** Config with env var refs resolves cleanly; engine receives literal values.
2. **Catalog-missing, SHOW CATALOGS succeeds (IDENT-01 primary):** Rich error with catalog list; chained cause.
3. **Catalog-missing, SHOW CATALOGS fails (IDENT-01 D-06):** Outer error names both failures.
4. **Unresolved env var (adjacent to TEST-01):** `resolve_env_vars` raises `ValueError` — not strictly a Phase 14 new behavior, but a regression check worth a parametrized case.
5. **SQLAlchemyError at create_engine (TEST-02):** `ConnectionError` with host in message.
6. **Regression lock for IDENT-02 (D-15):** `list_schemas` produces schema list with zero `SHOW CATALOGS` executions.
7. **URL-mode catalog absence (edge of IDENT-01):** `databricks://...` URL without `?catalog=` → same `ConnectionError` as config path.

## Sources

### Primary (HIGH confidence)
- **In-repo code (read and verified):**
  - `src/db/dialects/databricks.py` lines 104-180 (`_kwargs_from_url`), 182-265 (`create_engine`)
  - `src/db/metadata.py` lines 79-127 (`list_schemas`), 164-201 (`_list_databricks_catalogs`, `_databricks_default_catalog`)
  - `src/db/connection.py` lines 65 (`ConnectionError`), 327-385 (`connect_with_url`), 420-546 (`connect_with_config`, `_connect_databricks_from_config`, `_register_engine`)
  - `src/config.py` lines 70-80 (`DatabricksConnectionConfig`), 119-141 (`resolve_env_vars`)
  - `tests/unit/test_connect_with_config_databricks.py` (full file — engine-spy pattern, monkeypatch pattern)
- **In-repo planning docs:**
  - `.planning/phases/14-connect-time-hardening-databricks/14-CONTEXT.md` (17 locked decisions)
  - `.planning/REQUIREMENTS.md` (IDENT-01, IDENT-02, TEST-01, TEST-02)
  - `.planning/ROADMAP.md` §Phase 14 success criteria
  - `.planning/codebase/TESTING.md` (framework, fixture conventions)
- **Databricks docs:** `SHOW CATALOGS` syntax and permissions model — docs.databricks.com SQL reference (cited inline).

### Secondary (MEDIUM confidence)
- None — the phase is entirely within already-read code and locked decisions.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all in pyproject.toml already.
- Architecture: HIGH — 17 decisions locked; only structural placement of `_require_databricks_catalog` is discretionary (D-04/D-08 constrain behavior).
- Pitfalls: HIGH — 5 pitfalls derived from in-code inspection, including the `connection.py:499` gap which is the only meaningful uncertainty (Assumption A1).
- Validation: HIGH — reqs map 1:1 to tests; engine-spy pattern proven.

**Research date:** 2026-05-11
**Valid until:** 2026-06-10 (30 days — implementation is narrow and stable; no external dependencies that could drift).
