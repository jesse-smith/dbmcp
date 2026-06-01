---
slug: phase14-list-schemas-shows-catalogs
status: resolved
trigger: |
  Defect B from Phase 14 UAT re-run (2026-05-15): `list_schemas` against a
  Databricks connection returns 20 entries that look like *catalog* names
  (bmtct, cerner_src, samples, system, ...) with `table_count: 0` and
  `view_count: 0`, instead of the schemas of the bound catalog. This
  violates Phase 14 invariant IDENT-02 (no SHOW CATALOGS fallback) and
  produces structurally wrong metadata results.

  Per chain D → C → A → B. D, C, and A have been root-cause-found. A is
  independent (config-layer "main" default). D is independent (host-
  deterministic conn_id + pool collision). C is downstream of D. B is
  the last defect and is in a different code path (metadata, not
  connection establishment).

  Strong prior: src/db/metadata.py:928 contains `dte_catalog = catalog
  or "main"  # Fall back to default catalog`. This is the third
  `or "main"` fallback in the codebase (after src/config.py:77 and
  :243). Hypothesis: list_schemas on Databricks executes a SHOW
  CATALOGS-style query whose result count (20) matches the workspace's
  catalog count, then misreports them as schemas with zero
  tables/views.
created: 2026-05-15
updated: 2026-05-15
goal: find_root_cause_only
---

# Debug Session: phase14-list-schemas-shows-catalogs

## Symptoms

DATA_START
**Expected behavior:**
- Per Phase 14 IDENT-02: `list_schemas` against a Databricks connection
  bound to catalog X must return X's schemas (e.g. for catalog `bmtct`,
  return the schemas defined in bmtct), not catalog names.
- Each entry should have a meaningful `table_count` and `view_count`.
- No SHOW CATALOGS fallback should exist anywhere in the metadata path.

**Actual behavior:**
- Sequence observed during Phase 14 UAT re-run on 2026-05-15:
  1. `connect_database(connection_name="databricks-test")` returns
     `connection_id: f255ae1dfbb3` (cold connect, catalog defaulted to
     "main" per Defect A).
  2. `list_schemas(connection_id=f255ae1dfbb3)` returns ~20 entries
     whose names match the workspace's *catalog* names (bmtct,
     cerner_src, samples, system, ...), each with `table_count: 0`
     and `view_count: 0`.
  3. The just-completed cold connect returned `schema_count: 20` in
     the success message — same number. Same data path almost certainly
     fires for both `connect_database`'s schema_count probe and
     `list_schemas`'s actual return.

**Errors:** None. Defect is silent.

**Timeline:**
- Surfaced 2026-05-15 during the Phase 14 UAT re-run after the prior
  Databricks TLS gap stopped reproducing. Co-occurred with Defects
  C, A, D being detected; this session investigates B in isolation.

**Reproduction:**
1. Configure `[connections.databricks-test]` in dbmcp.toml with any
   valid catalog (or with catalog commented out — Defect A will
   silently substitute "main").
2. Cold restart dbmcp server.
3. `connect_database(connection_name="databricks-test")` — note
   `schema_count: 20` in the message (suspicious — matches workspace
   catalog count, not catalog schema count).
4. `list_schemas(connection_id=...)` — observe entries that are
   workspace catalog names with `table_count: 0`.

**Suspected mechanism (priors):**
- `src/db/metadata.py:928` contains `dte_catalog = catalog or "main"`
  with a comment "Fall back to default catalog". This is the third
  `or "main"` fallback in the codebase. The pattern strongly suggests
  that the metadata layer has its OWN catalog handling distinct from
  the connection-establishment layer, and it may execute SHOW CATALOGS
  (or an equivalent) when its `catalog` argument is empty/None — even
  though the dialect connection establishment is now bound to a
  specific catalog.
- The `schema_count: 20` reported by the connect_database success
  message (which we already know defaulted to "main" via Defect A)
  matches the workspace catalog count, not main's actual schema count.
  This is consistent with the metadata path issuing a SHOW CATALOGS
  call and the result being relabeled as "schemas".
- Phase 14 IDENT-02 was supposed to remove SHOW CATALOGS fallback
  paths. Either the work missed the metadata layer, or the metadata
  layer's SHOW CATALOGS lives in a path the IDENT-02 audit didn't
  inspect.

**Open questions for this session:**
- Q1: What does `list_schemas` actually execute on a Databricks
  connection? Trace from the MCP tool entry point
  (src/mcp_server/schema_tools.py `list_schemas`) through the dialect
  metadata path to the actual SQL.
- Q2: Where is the "20" coming from? Is it (a) SHOW CATALOGS, (b)
  SHOW SCHEMAS without a catalog qualifier listing all catalogs as
  schemas, (c) SHOW SCHEMAS IN <catalog> returning incorrect data,
  or (d) Information Schema with the wrong filter?
- Q3: Does `src/db/metadata.py:928` (`or "main"`) actually fire in
  the live repro, or is it an unrelated cosmetic fallback? Trace the
  caller(s) and arguments.
- Q4: Is the table_count: 0 / view_count: 0 a separate bug (e.g.
  the count query runs but matches nothing because it's filtering on
  a catalog-as-schema name) or a downstream consequence of Q1/Q2?
- Q5: How does SQL Server's `list_schemas` differ such that it
  returns the right thing (the user has not reported SQL Server
  symptoms here)?

**Likely files:**
- `src/mcp_server/schema_tools.py` — `list_schemas` MCP tool entry
  point, output formatting.
- `src/db/metadata.py` — schema/table introspection layer, particularly
  around line 928 with the `or "main"` fallback.
- `src/db/dialects/databricks.py` — dialect-level metadata methods
  (e.g. `list_schemas`, `list_tables` on the dialect strategy).
- `src/db/dialects/base.py` (or equivalent abstract) — dialect strategy
  interface.

**Cross-reference:**
- `.planning/debug/phase14-conn-id-determinism.md` (Defect D, root_cause_found, independent)
- `.planning/debug/phase14-url-catalog-ignored.md` (Defect C, root_cause_found, downstream of D)
- `.planning/debug/phase14-catalog-required-bypass.md` (Defect A, root_cause_found, INDEPENDENT — config-layer "main" default in src/config.py:77 and :243)

  IMPORTANT for this investigation: A's revised diagnosis identified a
  THIRD `or "main"` fallback at src/db/metadata.py:928 that was flagged
  as out-of-scope-for-A but in-scope-for-B. Start there.
DATA_END

## Current Focus

hypothesis (REVISED 2026-05-15 after static trace): The strong prior
  about `src/db/metadata.py:928` (`or "main"`) was MISLEADING. That
  fallback is in a different function (related to `dte_catalog` /
  table-existence path), NOT in `list_schemas`. The actual
  `list_schemas` Databricks path is well-formed: it reads
  `self.engine.url.query["catalog"]` (loud KeyError if missing) and
  executes `SHOW SCHEMAS IN \`<catalog>\``. There is no SHOW CATALOGS
  call site in the metadata layer.

  This means one of two scenarios produces the symptom:

  (B-i) The connection_id `f255ae1dfbb3` is bound to a catalog whose
    name's `SHOW SCHEMAS IN` legitimately returns 20 names that
    happen to coincide with workspace catalog names — implausible
    on its face but the only path consistent with code as written
    when the engine URL truly has `catalog=main`.

  (B-ii) The connection_id `f255ae1dfbb3` is NOT bound to "main".
    Per Defect D, conn_id is hashed from `(host, http_path)` only, so
    the engine pool may have reused an engine bound to a different
    catalog from a prior session in the same Claude Code lifecycle.
    If the user's prior worktree state had `catalog = "bmtct"`
    uncommented, that engine would still be in the pool and
    `_engine_catalog()` would return "bmtct" — but `SHOW SCHEMAS IN
    \`bmtct\`` would return bmtct's schemas, which still wouldn't
    have names like `samples`/`system`.

  Neither static-analysis scenario fully accounts for the observed
  20 catalog-named entries. The decisive question is empirical:
  what SQL string does the live engine execute, and what does the
  underlying warehouse return for it?

test: Need to capture the actual executed SQL. Two ways forward:
  (1) Ask the user to enable SQLAlchemy engine echo / DEBUG logging
      and re-run `list_schemas`, capturing the raw SQL and the
      raw result rows.
  (2) Ask the user to manually run `execute_query` on the same
      connection_id with two probe queries — `SELECT current_catalog()`
      and `SHOW CATALOGS` — to confirm what catalog the session
      is bound to and what the workspace's catalog list looks like.
expecting: One of:
  - current_catalog() returns "main" and the workspace really does
    have a `main` catalog whose schemas happen to be named like
    catalogs (extremely unlikely, but rules out a code bug).
  - current_catalog() returns something other than "main", revealing
    a Defect-D-style pool-reuse interaction with B (would make B
    downstream of D after all).
  - current_catalog() returns the right value but `SHOW SCHEMAS IN
    \`main\`` actually returns workspace catalog names — would
    indicate a connector-level quirk (databricks-sqlalchemy /
    databricks-sql-connector behavior) rather than a dbmcp bug.
next_action: CHECKPOINT — request user empirical data via execute_query
  probes on the live connection_id f255ae1dfbb3.

## Evidence

- timestamp: 2026-05-15 [investigation]
  source: src/mcp_server/schema_tools.py:234-290 (list_schemas MCP tool)
  finding: |
    The MCP `list_schemas` tool calls `metadata_svc.list_schemas(
    connection_id=connection_id, catalog=catalog)` with `catalog=None`
    when the user does not pass an explicit catalog override. No
    transformation of the catalog argument occurs at the MCP boundary.

- timestamp: 2026-05-15 [investigation]
  source: src/db/metadata.py:79-118 (MetadataService.list_schemas dispatcher)
  finding: |
    The Databricks branch (line 104-106) does:
        effective_catalog = catalog or self._engine_catalog()
        result = self._list_schemas_databricks(connection_id, effective_catalog)
    `catalog` is None per the MCP-layer call, so `effective_catalog`
    is whatever `self._engine_catalog()` returns. This is the FIRST
    `or` fallback — but it falls back to the engine-bound catalog,
    NOT to a string literal. There is no `or "main"` here.

- timestamp: 2026-05-15 [investigation]
  source: src/db/metadata.py:155-162 (_engine_catalog)
  finding: |
    `_engine_catalog()` is `return self.engine.url.query["catalog"]`.
    KeyError propagates uncaught (verified — no try/except around the
    call site). Per Phase 14 IDENT-01 invariant, the engine is built
    with `catalog=` always set in the URL query.

- timestamp: 2026-05-15 [investigation]
  source: src/db/metadata.py:164-214 (_list_schemas_databricks)
  finding: |
    Single SQL site: `text(f"SHOW SCHEMAS IN {quoted_catalog}")` at
    line 180, where `quoted_catalog = self._dialect.quote_identifier(
    catalog)` (backtick-wrapped). For each schema row, the function
    then queries `SELECT table_schema, SUM(...) FROM
    \`<catalog>\`.information_schema.tables GROUP BY table_schema`.
    If that information_schema call raises SQLAlchemyError, schemas
    are returned with zero counts (line 194-198, logger.warning).

    NB: This `try/except SQLAlchemyError` swallowing the
    information_schema failure DOES match the user's `table_count: 0`
    / `view_count: 0` observation. So whatever schemas SHOW SCHEMAS
    returns, the counts query is silently failing for them.

- timestamp: 2026-05-15 [investigation]
  source: codebase grep for SHOW CATALOGS / SHOW SCHEMAS
  finding: |
    Three occurrences total in src/:
      - src/db/connection.py:536, 539, 545 (probe in
        `_require_databricks_catalog`, only fires when create_engine
        raised ValueError because catalog was empty).
      - src/db/dialects/databricks.py:290 (`list_catalogs` helper,
        called only by `_require_databricks_catalog`).
      - src/db/metadata.py:180 (the `SHOW SCHEMAS IN <catalog>` site
        analyzed above).
    There is NO SHOW CATALOGS fallback in the metadata layer. The
    Phase 14 IDENT-02 audit removed those paths correctly.

- timestamp: 2026-05-15 [investigation]
  source: src/db/metadata.py:928 (the strong-prior site)
  finding: |
    The `dte_catalog = catalog or "main"` line is in a DIFFERENT
    function (table-existence / table-schema path, around the
    `dte_catalog` / `table_exists` region near line 928), not in
    list_schemas. It is not on the list_schemas call path. The
    strong prior pointed at the wrong site.

    This `or "main"` is still a bug — it's a third fallback that
    Phase 14 IDENT-01/IDENT-02 should have eliminated — but it
    cannot be the cause of Defect B's `list_schemas` symptom. It
    affects `get_table_schema` / `table_exists` paths instead. May
    surface as a separate defect in those tools but is out of scope
    for B's current symptom.

- timestamp: 2026-05-15 [investigation]
  source: src/db/dialects/databricks.py:246-251 (engine URL construction)
  finding: |
    `create_engine` builds the SQLAlchemy URL as:
        databricks://token:<token>@<host>?http_path=...&catalog=<catalog>&schema=...
    `catalog` is validated non-empty at line 242-243 (raises
    ValueError("Databricks catalog is required")). So the engine
    URL ALWAYS has a non-empty catalog query param at construction
    time. `_engine_catalog()` cannot return "" or raise KeyError on
    a successfully-built engine.

- timestamp: 2026-05-15 [investigation]
  source: .venv/lib/python3.13/site-packages/databricks/sqlalchemy/base.py:104-122
  finding: |
    Vendored `databricks-sqlalchemy` `create_connect_args` reads
    `url.query.get("catalog")` and passes it as `catalog=` to
    `databricks.sql.connect()`. So our URL's `catalog=main` is
    propagated to the underlying connector session. There is no
    silent rewrite at the SQLAlchemy dialect layer.

- timestamp: 2026-05-15 [analysis]
  source: cross-reference Defect D's pool-reuse mechanism
  finding: |
    Per Defect D, connection_id is hashed from (host, http_path) only;
    the engine pool dedupes on connection_id. If a prior connect call
    in the same server lifecycle bound the engine to catalog X, ALL
    subsequent connects for the same host+http_path reuse that
    engine regardless of the requested catalog. So `_engine_catalog()`
    returns the catalog of the FIRST connect, not the most recent
    requested catalog.

    However, the orchestrator stated this was a fresh cold-pool
    repro post-restart, and the connect_database success message
    referenced "main". On a truly cold pool with catalog commented
    out, Defect A's "main" default applies and the engine binds to
    "main". So the engine SHOULD be bound to "main" in this state.

- timestamp: 2026-05-15 [analysis]
  source: symptom-vs-static-trace mismatch
  finding: |
    Static trace shows `list_schemas` MUST execute exactly:
        SHOW SCHEMAS IN `main`
    against an engine bound to catalog "main". The user observes 20
    rows whose names look like workspace catalog names (bmtct,
    cerner_src, samples, system). This mismatch cannot be resolved
    from static analysis alone — it requires live SQL/warehouse
    inspection. Specifically: `samples` and `system` are well-known
    Databricks workspace-level CATALOG names, and a `main` catalog
    typically does not contain SCHEMAS named `samples` or `system`.
    Either the executed SQL is not what the code says it is, or the
    engine is not bound to "main" as the orchestrator believes, or
    the workspace's `main` catalog has unusual content.

## Eliminated

- src/db/metadata.py:928 (`dte_catalog = catalog or "main"`) — NOT on
  list_schemas call path. (This `or "main"` is still a design smell
  for IDENT-01 hygiene, but it's a separate latent issue affecting
  table_exists / get_table_schema, not list_schemas.)
- A SHOW CATALOGS call site in the metadata layer — does not exist.
  IDENT-02 removed it correctly. The only SHOW CATALOGS call site in
  the codebase is in the catalog-required ValueError enrichment path,
  gated on `create_engine` raising — a path Defect A bypasses by
  defaulting catalog to "main".
- A "schemas without IN-clause" path — does not exist; the SQL is
  unconditionally `SHOW SCHEMAS IN <quoted_catalog>`.

## Resolution

status: root_cause_found
specialist_hint: python

### Empirical evidence (2026-05-15, second cycle)

- Probe (2) `SHOW SCHEMAS IN \`main\`` against the live engine raised
  `[NO_SUCH_CATALOG_EXCEPTION] Catalog 'main' was not found.
  SQLSTATE: 42704` — confirms the engine reaches the workspace and
  the workspace has no `main` catalog.
- Probe (3) `SHOW CATALOGS` returned exactly 20 rows in the order:
  `bmtct, caboodle_src, cerner_src, clarity_src, data_products,
  hive_metastore, ica, nucleus_config, nucleus_fileshare, oncore_src,
  packages_libraries, playground, samples, sceo_dev, sjlife_freeze,
  svwpstem03_src, svwpstem04_src, system, trialmaster_src, warehouse`.
- The user's `list_schemas` output is a strict subset of those 20
  names, with `table_count: 0` and `view_count: 0` on every row, and
  the row count is exactly 20.
- Probe (1) `SELECT current_catalog()` could not run because of an
  unrelated `execute_query` cross-dialect leak (MSSQL `SELECT TOP
  (1000)` prefix injected into a Databricks query). Captured as a
  separate finding below; does not affect this defect.

### Decisive code-archaeology finding

- timestamp: 2026-05-15 [investigation, second cycle]
  source: git log src/db/metadata.py
  finding: |
    Commit `74f5c97` (May 1, 2026 era — "fix(metadata): Databricks
    list_schemas falls back to SHOW CATALOGS") introduced a method
    `MetadataService._list_databricks_catalogs` that ran
    `text("SHOW CATALOGS")` and returned each catalog as a pseudo-
    Schema with `table_count=0, view_count=0`. The dispatch in
    `list_schemas` was:

        if catalog:
            result = self._list_schemas_databricks(connection_id, catalog)
        else:
            default_catalog = self._databricks_default_catalog()
            try:
                result = self._list_schemas_databricks(connection_id, default_catalog)
            except SQLAlchemyError as exc:
                logger.info(... "falling back to SHOW CATALOGS for discovery.")
                result = self._list_databricks_catalogs(connection_id)

    Commit `6cfe60c` ("feat(14-02): collapse list_schemas Databricks
    branch to single deterministic path", 2026-05-13 15:54 -0500) is
    the Phase 14 IDENT-02 fix that DELETED `_list_databricks_catalogs`
    and the surrounding try/except, replacing the dispatch with the
    current single-path code at metadata.py:104-106.

    The deleted fallback's behavior is an EXACT match for the user's
    observed symptom: SHOW CATALOGS executed, each row materialized as
    a `Schema` with zero counts.

### root_cause

  Defect B is **stale-process drift, not a code bug on disk**. The
  on-disk code in `src/db/metadata.py` is correct post-IDENT-02:
  `_list_databricks_catalogs` is removed, the try/except SHOW CATALOGS
  fallback is removed, and `list_schemas` deterministically runs
  `SHOW SCHEMAS IN \`<catalog>\`` and propagates errors.

  However, the running dbmcp MCP server process is executing the
  PRE-IDENT-02 code from commit `74f5c97`. When invoked with
  catalog="main" (Defect A's config-layer default for this
  catalog-commented-out config), the in-memory `_list_schemas_databricks`
  raises `NO_SUCH_CATALOG_EXCEPTION` (a SQLAlchemyError), is caught by
  the in-memory try/except, and the fallback `_list_databricks_catalogs`
  runs `SHOW CATALOGS` and returns each catalog as a pseudo-schema
  with zero counts. That is exactly the user's 20-entry result.

  Why the process is stale: dbmcp is installed as an editable package
  (verified via .venv/__editable__.dbmcp-0.1.0.pth → src/), so on-disk
  source changes are picked up at *next module import*. But the
  long-running MCP server process imported `src/db/metadata.py` once
  at startup; subsequent file edits do not invalidate the in-memory
  module. The MCP server process must be terminated and restarted at
  the OS level to pick up `6cfe60c`'s changes. A Claude Code UI
  restart does not by itself reliably re-spawn stdio MCP servers in
  every Claude Code version, and there's no evidence the user actually
  restarted the underlying Python process today.

  This also retroactively re-frames Defect A's "cold-pool" repro: the
  pool was cold (no engine cached) but the *process* was warm
  (pre-IDENT-02 metadata.py loaded). On a truly cold process with
  on-disk code, `connect_database` with catalog commented out would
  default to "main" via Defect A's config layer, then `list_schemas`
  would raise NO_SUCH_CATALOG and `connect_database` would return
  status:error, NOT status:success/schema_count:20. Defect A's symptom
  of "connected to main / schema_count: 20" is conditioned on the
  pre-IDENT-02 SHOW CATALOGS fallback being present in the running
  process.

  Mechanism summary:
    1. User runs `connect_database(connection_name="databricks-test")`
       with `catalog` commented out in dbmcp.toml.
    2. Defect A's `DatabricksConnectionConfig.catalog: str = "main"`
       supplies "main" → `dialect.create_engine(catalog="main")` → engine
       URL has `catalog=main` → engine session bound to non-existent
       `main` catalog.
    3. `_sync_connect()` calls `metadata_svc.list_schemas()`.
    4. **Stale in-memory code path** (the bug):
       a. `_list_schemas_databricks(catalog="main")` runs
          `SHOW SCHEMAS IN \`main\``.
       b. Workspace has no `main` catalog → `NO_SUCH_CATALOG_EXCEPTION`
          (SQLAlchemyError).
       c. In-memory try/except catches it, calls
          `_list_databricks_catalogs(connection_id)`.
       d. That runs `SHOW CATALOGS` → 20 rows → wraps each as a
          pseudo-Schema with table_count=0/view_count=0.
       e. `connect_database` returns success with `schema_count: 20`.
    5. User then calls `list_schemas(connection_id=...)` directly →
       same stale path → same 20 pseudo-schemas.

### What B is NOT

- B is NOT downstream of Defect A in the way originally framed.
  Defect A (config "main" default) is independently a real bug, but
  with on-disk IDENT-02 code, A's "main" default would manifest as a
  loud `NO_SUCH_CATALOG` error on workspaces lacking a `main` catalog,
  not as 20 silent pseudo-schemas. The silent-pseudo-schema symptom
  requires the stale fallback.
- B is NOT downstream of Defect D's pool reuse. The behavior reproduces
  on a cold pool. Pool reuse is independent.
- B is NOT a bug at metadata.py:928. That `or "main"` is in the
  `dte_catalog` / table-existence path; it's a separate IDENT-01
  hygiene issue but does not contribute to B's symptom.

### fix

  fix: |
  Two layers, both required:

  (1) Operational (immediate): terminate and restart the dbmcp MCP
      server *process*. This drops the stale module from memory and
      reloads the post-IDENT-02 code. After restart, with catalog
      commented out in dbmcp.toml and Defect A still unfixed, the
      symptom changes: `connect_database` will return status:error
      with the NO_SUCH_CATALOG message bubbling out of list_schemas
      (because Defect A is still defaulting to "main"). That's the
      correct loud-failure behavior IDENT-02 was designed to produce;
      Defect A then needs its own fix to stop substituting "main".

      Practical guidance: in Claude Code, run the MCP "restart server"
      action for the dbmcp server, OR kill the dbmcp process by PID
      and let Claude Code respawn it. Verify by running `connect_database`
      against `databricks-test` (catalog commented out) and confirming
      the response is status:error containing NO_SUCH_CATALOG, not
      status:success/schema_count:20.

  (2) Process-level (preventive): the on-disk code is already correct;
      no source changes are required for Defect B itself. However,
      this incident exposes a **process-staleness foot-gun** that
      makes Phase 14 UAT results unreliable until mitigated. Consider
      one of:
        - Adding a startup banner that logs the metadata.py git SHA
          (or a Phase-14-specific build marker) so the user can
          immediately tell whether the running process predates a
          known-good commit.
        - Adding an MCP tool (e.g. `_diagnose_server`) that returns
          the git SHA / mtime of the loaded `src.db.metadata` module
          for fast staleness detection during UAT.
        - Documenting in the Phase 14 UAT checklist that all UAT runs
          MUST be preceded by an OS-level dbmcp process restart, not
          just a Claude Code UI restart.

      Pick the minimal one (mtime-of-loaded-module logged at startup
      is probably enough). Out of scope for B's defect closure but
      strongly recommended before re-running Phase 14 UAT.

  Status: B is independent of D and independent of A *as a code
  defect*. The code defect was already fixed in `6cfe60c`. The defect
  that surfaced today is environmental (stale process). A still needs
  fixing on its own merits — once A is fixed, "main" will no longer
  be auto-injected and the NO_SUCH_CATALOG symptom will not arise
  for catalog-commented-out configs in the first place.

### Side findings (out of scope, captured for traceability)

- **execute_query LIMIT/TOP cross-dialect leak.** When the user ran
  `SELECT current_catalog()` via `execute_query` against the Databricks
  connection, the response showed the query was rewritten to
  `SELECT TOP (1000) current_catalog() AS bound_catalog`, producing a
  Databricks `[PARSE_SYNTAX_ERROR]`. MSSQL-style `TOP` clause is being
  injected into Databricks queries — the auto-LIMIT path appears not
  to be dialect-aware. Worth a separate session.

- **metadata.py:928 `or "main"` fallback.** Still present, on the
  table-existence / dte_catalog path (NOT list_schemas). Surveyed
  and confirmed not contributing to Defect B. Leave as a follow-up
  IDENT-01 hygiene item; recommend a separate small session to confirm
  whether `get_table_schema`/`table_exists` exhibit the same
  silent-default-to-"main" behavior, and remove the fallback in favor
  of `_engine_catalog()` for consistency with `list_schemas`.
