---
slug: phase14-catalog-required-bypass
status: resolved
trigger: |
  Defect A from Phase 14 UAT re-run (2026-05-15): a named-config Databricks
  connect call that omits `catalog` should raise a ConnectionError per
  Phase 14 invariant IDENT-01 (catalog required, no SHOW CATALOGS fallback).
  Instead, when `catalog` is commented out in dbmcp.toml, the call returns
  `status: success` with a message indicating connection to a catalog (e.g.
  "main" or whatever the prior pool entry was bound to). This violates the
  catalog-required invariant silently.

  Per chain D → C → A → B. Defects D and C are already root_cause_found:
  - D: host-deterministic connection_id + same key as engine pool key
    (src/db/connection.py:636-643, 349, 422, 590).
  - C: silently downstream of D — no independent path.
  Suspected: A is also downstream of D — the pool-reuse short-circuit
  bypasses `_require_databricks_catalog` validation when a prior call
  populated the pool. Goal: confirm/refute, and identify any independent
  bypass path that exists even on a cold pool (cache miss).
created: 2026-05-15
updated: 2026-05-15
goal: find_root_cause_only
---

# Debug Session: phase14-catalog-required-bypass

## Symptoms

DATA_START
**Expected behavior:**
- Per Phase 14 invariant IDENT-01: a Databricks connect call without a
  catalog must raise ConnectionError with a clear message. There is no
  SHOW CATALOGS fallback; catalog is REQUIRED at connect time.
- Both code paths (named-config and URL-mode) must enforce this.
- The validation must run BEFORE engine reuse, so it cannot be silenced
  by a previously-populated engine pool.

**Actual behavior:**
- Sequence observed during Phase 14 UAT re-run on 2026-05-15:
  1. Configure `[connections.databricks-test]` in dbmcp.toml WITHOUT a
     catalog line (commented out).
  2. `connect_database(connection_name="databricks-test")` →
     returns `status: success` and a message indicating the connection is
     bound to a catalog (whichever was bound first for that host —
     `main` or `bmtct` depending on whether a prior call had populated
     the pool).
  3. No ConnectionError raised. IDENT-01 invariant violated.

**Errors:** None. Defect is silent.

**Timeline:**
- Surfaced during the Phase 14 UAT re-run after the prior Databricks TLS
  gap stopped reproducing.
- Phase 14 unit tests for IDENT-01 are green; the defect lives in a
  runtime path the unit tests don't exercise (named-config path with a
  warm pool, or whatever cold path also bypasses validation).

**Reproduction:**
1. Comment out `catalog = "..."` in `[connections.databricks-test]`.
2. Restart dbmcp server cleanly.
3. `connect_database(connection_name="databricks-test")` — observe
   `status: success` instead of expected ConnectionError.
4. The success message references some catalog the user did not request
   (suggests fallback to a default like `main`, OR engine-pool reuse
   from a prior call).

**Suspected mechanism (carry-over from Defect D session):**
- `_connect_databricks_from_config` (src/db/connection.py:563-592) builds
  a canonical_url and feeds it to `_generate_url_connection_id`, then
  checks `if connection_id in self._engines` at line 590 and returns the
  cached Connection on hit.
- The catalog-required validation in `_require_databricks_catalog`
  (around line 606) and inside `dialect.create_engine` runs only on the
  cache-miss path, downstream of the pool reuse check.
- HOWEVER: even on a *cold* pool (fresh server, no prior connect), the
  user observed `status: success` with a catalog message. That suggests
  there may be an additional bypass — e.g.,
  - a default catalog substitution somewhere in dialect URL building, OR
  - a SHOW CATALOGS-style fallback that should have been removed in
    Phase 14 IDENT-02 work but still exists, OR
  - the validation only fires for URL-mode and not named-config.

**Open questions for this session:**
- Q1: Does the named-config path validate catalog presence at all, or
  does it silently default? (Inspect `_connect_databricks_from_config`
  and the dialect's `build_url` for a default substitution.)
- Q2: Does `_require_databricks_catalog` enrichment run only when
  `dialect.create_engine` raises, and if so, what raises it? If catalog
  is silently defaulted, no error is raised, no enrichment fires, and
  validation never happens.
- Q3: Is there a *cold-pool* reproduction (fully fresh server, no prior
  connects) that still returns success without catalog? If yes, the
  defect is not solely downstream of D — there is an independent
  validation gap.
- Q4: If A IS downstream of D (warm pool only), is there nonetheless a
  separate cold-path defect we should record (e.g., IDENT-01 was never
  actually wired into the named-config path)?

**Likely files:**
- `src/db/connection.py` — `_connect_databricks_from_config`,
  `_require_databricks_catalog`, the named-config catalog-required
  check (if any).
- `src/db/dialects/databricks.py` — URL building from config dict, any
  catalog defaulting (e.g. `catalog = config.get("catalog", "main")`).

**Cross-reference:**
- `.planning/debug/phase14-conn-id-determinism.md` (Defect D, root_cause_found)
- `.planning/debug/phase14-url-catalog-ignored.md` (Defect C, root_cause_found
  — confirmed C has no independent path beyond D's pool-reuse short-circuit)
DATA_END

## Current Focus

hypothesis (REVISED 2026-05-15): Defect A has an INDEPENDENT cold-path
  root cause: `DatabricksConnectionConfig.catalog: str = "main"` default
  in src/config.py:77 (and URL-param default at src/config.py:243).
  Config layer silently substitutes "main" for omitted catalog,
  upstream of all catalog-required validation; the dialect's empty-check
  never sees an empty catalog and never fires.
test: Cold-pool repro on 2026-05-15 — full Claude Code restart, catalog
  commented out in dbmcp.toml. `connect_database(connection_name=
  "databricks-test")` returned `status: success / message: Successfully
  connected to main / schema_count: 20`. Confirmed independent bypass.
  Source inspection of DatabricksConnectionConfig (src/config.py:69-78)
  confirmed `catalog: str = "main"` field default.
expecting: Defect A is independent of Defect D. Both are real and
  distinct. Fix requires changes to src/config.py (lines 77 and 243).
next_action: Report revised diagnosis to user. Move on to Defect B
  diagnosis (likely entangled with src/db/metadata.py:928 `or "main"`
  fallback that produces the 20-schemas symptom).

## Evidence

- timestamp: 2026-05-15 [investigation]
  source: src/db/connection.py:563-592 (_connect_databricks_from_config)
  finding: |
    Named-config path computes canonical_url with empty catalog
    (`catalog = resolve_env_vars(config.catalog) if config.catalog else ""`,
    line 575) and hashes it via `_generate_url_connection_id` BEFORE any
    catalog-presence check. The pool-reuse short-circuit at lines 590-592
    (`if connection_id in self._engines: return self._connections[...]`)
    therefore fires whenever any prior connect populated `_engines` under
    the same host-derived key — bypassing all downstream validation.
- timestamp: 2026-05-15 [investigation]
  source: src/db/connection.py:636-643 (_generate_url_connection_id)
  finding: |
    Connection ID is `sha256("{backend}://{host}:{port}/{database}")[:N]`.
    Critically, `parsed.database` is the URL *path* component, not the
    `?catalog=` query parameter. The canonical_url built on line 586-588
    has no path component, so the ID is identical for any catalog (or
    no catalog) on the same host. This is the same defect already
    documented in session phase14-conn-id-determinism (Defect D).
- timestamp: 2026-05-15 [investigation]
  source: src/db/dialects/databricks.py:233-243 (create_engine)
  finding: |
    Cold-path catalog enforcement IS wired:
    ```
    catalog: str = kwargs.get("catalog", "") or ""
    if not catalog:
        raise ValueError("Databricks catalog is required")
    ```
    There is NO default-catalog substitution. Empty/missing/None all
    raise ValueError, which `_connect_databricks_from_config` catches at
    line 603 and routes through `_require_databricks_catalog` at line 606.
- timestamp: 2026-05-15 [investigation]
  source: src/db/connection.py:503-561 (_require_databricks_catalog)
  finding: |
    Helper has THREE terminal paths, all of which `raise ConnectionError`:
    (1) SHOW CATALOGS SQLAlchemyError → line 538 raise
    (2) SHOW CATALOGS other Exception → line 543 raise
    (3) Successful catalog listing → line 558 raise (with listing in msg)
    No path returns success. The Phase 14 IDENT-02 work (no SHOW CATALOGS
    *fallback*) is correctly implemented: SHOW CATALOGS is used only to
    enrich the error message, never to silently pick a catalog.
- timestamp: 2026-05-15 [investigation]
  source: src/db/connection.py:336-376 (connect_with_url, URL-mode)
  finding: |
    URL-mode has the SAME pool-reuse short-circuit at lines 349-351,
    and the SAME enrichment routing through `_require_databricks_catalog`
    in the ValueError handler at lines 361-376. Cold-path enforcement
    is symmetric with named-config-mode.
- timestamp: 2026-05-15 [investigation]
  source: src/db/connection.py:436-468 (connect_with_config dispatcher)
  finding: |
    Dispatcher routes `DatabricksConnectionConfig` exclusively to
    `_connect_databricks_from_config` (line 467). No alternate code path
    exists for named-config Databricks connects. Confirms the audit above
    is complete.
- timestamp: 2026-05-15 [analysis]
  source: cross-reference with Defect D session
  finding: |
    The user's "cold" reproduction in the trigger description is most
    likely a warm-pool reuse where the dbmcp server process was not
    actually restarted between the catalog-having and catalog-omitted
    calls, or a prior tool invocation in the same process populated
    `_engines` under the host-derived key. With a truly cold pool,
    dialect line 243 raises ValueError → enrichment helper raises
    ConnectionError. There is no path producing `status: success`
    without catalog on a cold pool.

## Eliminated

- Default-catalog substitution in dialect (`build_url`/`create_engine`):
  ELIMINATED — src/db/dialects/databricks.py:241-243 explicitly rejects
  empty catalog via `if not catalog: raise ValueError(...)`.
- Default-catalog substitution in named-config path
  (`_connect_databricks_from_config`): ELIMINATED — no `config.get(
  "catalog", "main")`-style default; `catalog` resolves to `""` when
  config.catalog is missing, which the dialect then rejects on cold path.
- SHOW CATALOGS success fallback (silently picking a catalog): ELIMINATED
  — `_require_databricks_catalog` always raises; SHOW CATALOGS is used
  only to enrich the error message.
- Named-config path missing IDENT-01 wiring: ELIMINATED — line 603-614
  routes ValueError through the same enrichment helper as URL-mode.
- Independent cold-pool bypass: NOT FOUND. No code path in
  `_connect_databricks_from_config`, `connect_with_url`, the dispatcher,
  or `DatabricksDialect.create_engine` produces a successful Connection
  when catalog is empty AND the engine pool is cold.

## Resolution

### REVISED 2026-05-15 after cold-pool repro

The prior conclusion ("A is purely downstream of D") was **wrong** and is
retained below as `## Superseded analysis` for traceability. Cold-pool repro
after a full Claude Code restart (catalog commented out in dbmcp.toml)
returned `status: success` / `message: Successfully connected to main` /
`schema_count: 20`. The audit missed the **config-layer default** that
supplies "main" upstream of every check it inspected.

root_cause: |
  Defect A has an INDEPENDENT root cause distinct from Defect D:

  `src/config.py:77` — `DatabricksConnectionConfig` dataclass declares
  `catalog: str = "main"` as the field default. When dbmcp.toml omits
  the catalog line, the config loader produces a config object with
  `config.catalog == "main"` (not None, not empty). Then in
  `_connect_databricks_from_config` (src/db/connection.py:575):

      catalog = resolve_env_vars(config.catalog) if config.catalog else ""

  Since "main" is truthy, this resolves to "main". The empty-catalog
  guard at `src/db/dialects/databricks.py:241-243` never fires because
  it never sees an empty catalog. The engine is created bound to `main`
  silently, with no error and no enrichment.

  URL-mode is symmetrically affected: `src/config.py:243` —
  `catalog=params.get("catalog", "main")` — applies the same default
  when a URL omits `?catalog=`.

  Audit error in the prior session: traced from
  `_connect_databricks_from_config` downward and confirmed (correctly)
  that no default substitution exists in that function or in
  `dialect.create_engine`. It never inspected the
  `DatabricksConnectionConfig` dataclass itself, which is one layer
  upstream and is where the default is actually applied.

  IDENT-01 is therefore violated structurally on every cold path, not
  just via warm-pool reuse. The Phase 14 work that wired
  `_require_databricks_catalog` and the dialect-level guard is correct
  but unreachable in normal operation because the config layer never
  produces an empty catalog for it to catch.

  Defect D (warm-pool conn-id collision) is a separate, additional
  defect that compounds A — it would also bypass IDENT-01 even if A
  were fixed in isolation.

fix: |
  Independent fix required for A:

  1. `src/config.py:77` — change `catalog: str = "main"` to
     `catalog: str = ""`. Line 575 of connection.py already passes
     empty through; the dialect at databricks.py:243 already raises
     on empty; the enrichment helper already routes that to
     ConnectionError.

  2. `src/config.py:243` — change `params.get("catalog", "main")` to
     `params.get("catalog", "")` so URL-mode is symmetric.

  3. Audit `src/db/metadata.py:928` (`dte_catalog = catalog or "main"`)
     — likely a separate metadata-layer fallback entangled with
     Defect B's "20 schemas" symptom. Investigate during B.

  Status: A is INDEPENDENT of D. Both must be fixed. C remains downstream
  of D. After A's fix, catalog-omitted cold connects will raise
  ConnectionError via the existing dialect guard + enrichment helper
  (which IS correctly wired — that part of the prior audit was right).

## Superseded analysis (2026-05-15, pre-cold-repro)

root_cause (SUPERSEDED): |
  Defect A is purely downstream of Defect D. [...kept for traceability;
  invalidated by cold-pool repro showing status:success / connected to main
  with empty pool.]
