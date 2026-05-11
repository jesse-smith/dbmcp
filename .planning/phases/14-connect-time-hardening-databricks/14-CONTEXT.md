# Phase 14: Connect-time hardening (Databricks) - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Make Databricks connection setup strict about catalog: `connect_database` rejects Databricks connections without a catalog; `list_schemas` loses its silent catalog-listing fallback; two residual regression tests from the 2026-05-05 audit land. Phase 15 builds the cross-dialect identifier resolver on top of this — Phase 14 only closes the connect-time gap.

</domain>

<decisions>
## Implementation Decisions

### Catalog-missing detection
- **D-01:** The catalog-required check lives in `DatabricksDialect.create_engine`. One guard covers both URL mode and kwargs mode — both paths flow through this method. Missing **or** empty-string catalog both count as missing; no hidden default.
- **D-02:** Remove the `catalog: str = kwargs.get("catalog", "main")` default at `src/db/dialects/databricks.py:239`. Also remove the `query.get("catalog", "main")` default in `_kwargs_from_url` at line 149. The "main" fallback is exactly the class of silent-wrong-catalog bug IDENT-01 eliminates.
- **D-03:** `create_engine` raises plain `ValueError("Databricks catalog is required")` on missing/empty catalog. Consistent with the file's existing pattern (`ValueError("Missing required parameter: host")` etc.). Keeps `create_engine` IO-free — matches its current "pure validation + URL construction" shape.

### Error shape for IDENT-01 (enriched at connect layer)
- **D-04:** The rich "catalog required + here are your accessible catalogs" error is constructed at the connect layer — `connect_with_url` and `connect_with_config` share a helper (e.g., `_require_databricks_catalog(...)`) that catches the `ValueError` from `create_engine`, builds a bare engine without catalog, runs `SHOW CATALOGS`, and re-raises as `ConnectionError`. This keeps IO where IO already lives; mirrors the existing `SQLAlchemyError → ConnectionError` wrapping pattern at `src/db/connection.py:365,384`.
- **D-05:** Error body format: first 20 catalogs + `(N more)` suffix when truncated. Example:
  > `Databricks connection requires a catalog. Accessible catalogs: main, hive_metastore, samples, ... (and 4 more). Pass one via ?catalog= in the URL or catalog= in the config.`
- **D-06:** If `SHOW CATALOGS` itself fails (permissions, network, transient SQLAlchemy error), chain the original via `raise ConnectionError(...) from exc`. Error message names both problems: the missing catalog requirement and the listing failure.
- **D-07:** Error class at the connect layer is `ConnectionError` (the custom class at `src/db/connection.py:65`). Matches existing connect-time error wrapping. The dialect-level `ValueError` stays as last-line defense for any future bypass path.

### SHOW CATALOGS helper placement
- **D-08:** The `SHOW CATALOGS` helper lives as a method on `DatabricksDialect` — e.g. `DatabricksDialect.list_catalogs(engine) -> list[str]`. Dialect-specific SQL stays with the dialect; DISC-01's future `list_catalogs` tool will call this same method. Symmetrical with other dialect SQL already on `DialectStrategy`.

### Scope of the fallback removal
- **D-09:** Delete `_list_databricks_catalogs` method at `src/db/metadata.py:164-190`. It's unreachable post-IDENT-01.
- **D-10:** Delete the `try/except SQLAlchemyError` wrapper at `src/db/metadata.py:107-115`. `list_schemas` on Databricks becomes a single path: use the explicit `catalog=` param if provided, otherwise read the engine's connected catalog.
- **D-11:** Rename `_databricks_default_catalog` → `_engine_catalog`. Strip the `"main"` fallbacks — body becomes `return self.engine.url.query["catalog"]`. Let `KeyError` propagate naturally if the IDENT-01 invariant is ever broken (loud failure, not silent "main"). Keeps the named indirection (one caller today, but self-documenting) without the misleading dead code.
- **D-12:** Update the `list_schemas` docstring at `src/db/metadata.py:79-94`. Remove the "falls back to listing available catalogs" language. State the post-IDENT-01 invariant: catalog is always known.
- **D-13:** Keep `list_schemas(catalog=...)` as an optional parameter. Still useful for cross-catalog exploration post-connect; consistent with Phase 15's IDENT-05/06 direction of adding `catalog=` to more tools.

### Regression tests
- **D-14:** **IDENT-01 test** — add to `tests/unit/test_connect_with_config_databricks.py` (or a new `test_connect_databricks_catalog_required.py` — writer's call during planning). Assertions: (a) connect with catalog-less URL raises `ConnectionError`; (b) error message contains the SHOW CATALOGS output; (c) the underlying `ValueError` from `create_engine` is chained via `__cause__`; (d) when SHOW CATALOGS is patched to raise, the outer error message names both the missing-catalog requirement AND the listing failure.
- **D-15:** **IDENT-02 regression test** — spy on `engine.execute` (or on the dialect) during `list_schemas` on a Databricks connection. Assert no `SHOW CATALOGS` query is ever issued. Directly asserts the fallback code is gone. Lock the pre-IDENT-01 failure mode.
- **D-16:** **TEST-01** (`test_env_var_substitution_for_catalog_and_schema`) — add to existing `tests/unit/test_connect_with_config_databricks.py`. Set env vars `DBX_CATALOG` and `DBX_SCHEMA`, build `DatabricksConnectionConfig(catalog="${DBX_CATALOG}", schema_name="${DBX_SCHEMA}")`, spy on the engine factory, assert `captured_kwargs["catalog"]` and `captured_kwargs["schema"]` are the resolved values (not `${...}` literals).
- **D-17:** **TEST-02** (`test_sqlalchemy_error_wrapped_as_connection_error`) — add to same file. Patch `DatabricksDialect.create_engine` to raise `SQLAlchemyError("boom")`. Call `connect_with_config`. Assert `ConnectionError` raised; message contains the host string (the safe-URL form used in `connection.py:365,384`).

### Claude's Discretion
- Exact test file naming (one file vs two) and fixture factoring — let the planner/executor decide during implementation.
- Exact wording of the user-facing error messages — D-05 gives the template; small phrasing tweaks are fine.
- Whether `_require_databricks_catalog` becomes a standalone module function, a private method on `ConnectionManager`, or a helper on the dialect — structural placement is flexible as long as the behavior in D-04/D-06 holds.

</decisions>

<specifics>
## Specific Ideas

- Truncation at 20 catalogs is a pragmatic bound — Databricks workspaces rarely exceed that; the `(and N more)` suffix preserves the "list is informative but not exhaustive" framing.
- Chained exceptions (`raise ... from exc`) are the existing pattern at `src/db/connection.py:365,384` — reuse.
- Databricks workspaces without Unity Catalog use `hive_metastore` as the visible catalog; do not hardcode `main` as an example in tests or docs.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` §Phase 14 — Success criteria for Phase 14, dependency note for Phase 15.
- `.planning/REQUIREMENTS.md` §IDENT-01, IDENT-02, TEST-01, TEST-02 — Locked requirements this phase closes.

### Existing code the planner must read
- `src/db/dialects/databricks.py` — Current `create_engine` (kwargs + URL modes), `_kwargs_from_url`, the two `catalog` defaults being removed (lines 149, 239).
- `src/db/metadata.py` §`list_schemas`, `_list_databricks_catalogs`, `_databricks_default_catalog` (lines 79-201) — The fallback being deleted and the method being renamed.
- `src/db/connection.py` §`connect_with_url`, `connect_with_config` (lines 327-535) — Where the `_require_databricks_catalog` helper plugs in; existing `SQLAlchemyError → ConnectionError` wrapping pattern at lines 365 and 384.
- `src/config.py` §`DatabricksConnectionConfig`, `resolve_env_vars` — TEST-01 depends on env-var resolution path.
- `tests/unit/test_connect_with_config_databricks.py` — Existing Databricks connect-time tests; TEST-01 and TEST-02 land here (default destination).

### Project conventions
- `.planning/codebase/CONVENTIONS.md` — Style, naming, error-handling conventions.
- `.planning/codebase/TESTING.md` — Test placement, fixture patterns, coverage floor (85%, per Phase 13).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DatabricksDialect.create_engine` already does `ValueError`-based presence validation for `host`/`http_path` — add the catalog check in the same style for consistency.
- `connection.py` already has the `SQLAlchemyError → ConnectionError` wrapping pattern at `connect_with_url:365` and `connect_with_config:384` — extend the same pattern to catch `ValueError("catalog required")` + run `SHOW CATALOGS`.
- The existing `tests/unit/test_connect_with_config_databricks.py` has an engine-spy factory (`_make_engine_spy`) and a pattern for intercepting `DatabricksDialect.create_engine` via `monkeypatch.setattr` — reuse for IDENT-01 and TEST-01/02 tests.

### Established Patterns
- **Pure-validation `create_engine`**: no IO inside dialect `create_engine` methods. IO lives at `connect_with_*` in `connection.py`. Phase 14 preserves this.
- **Chained exceptions**: `raise ConnectionError(...) from exc` is the codebase pattern. Preserve in IDENT-01 error handling.
- **Dialect-owned SQL**: dialect-specific queries live on the DialectStrategy subclass (e.g. `DatabricksDialect`), not on the generic metadata or connection layers.
- **Safe-URL in error messages**: `connection.py:365,384` uses a `safe_url` form of the connection string in error messages. TEST-02 asserts the host appears — align with existing sanitization.

### Integration Points
- `DatabricksDialect.create_engine` — receives the new `ValueError` guard.
- `DatabricksDialect.list_catalogs` — new method; SQL helper for `SHOW CATALOGS`.
- `ConnectionManager.connect_with_url` / `connect_with_config` — each invokes the new shared `_require_databricks_catalog` helper at engine-creation time.
- `MetadataService.list_schemas` / `_engine_catalog` (renamed) — fallback code removed; single path for Databricks.
- `tests/unit/test_connect_with_config_databricks.py` — default home for IDENT-01, TEST-01, TEST-02 tests.

</code_context>

<deferred>
## Deferred Ideas

### Tech-debt follow-up (not Phase 14 or Phase 15)
- **Error-class inconsistency**: codebase mixes `ValueError` (dialect-level presence), custom `ConnectionError` (connect-time IO), and plain `ValueError` at orchestration. No `ConfigurationError` type exists despite "configuration" being a semantic category. Worth a look as a dedicated tech-debt pass — not in v2.1.
- **MSSQL-flavored naming in cross-dialect code**: "default catalog" vocabulary in Databricks code paths reads with MSSQL convention (where "default" implies a system-wide concept like `dbo`). Databricks has no workspace-wide default catalog — it's whatever the engine was built with. Phase 14 fixes the one instance (`_databricks_default_catalog → _engine_catalog`); audit for others in a future cleanup.

### Out of Phase 14 scope (already noted in roadmap/requirements)
- Cross-dialect `list_catalogs`/`list_databases` tool → `DISC-01` in backlog; will reuse the `DatabricksDialect.list_catalogs` helper introduced here.
- Identifier-resolver refactor (3/2/1-part parsing, conflict detection, per-dialect default schema) → Phase 15 (`IDENT-03` through `IDENT-07`). Depends on Phase 14.

</deferred>

---

*Phase: 14-connect-time-hardening-databricks*
*Context gathered: 2026-05-11*
