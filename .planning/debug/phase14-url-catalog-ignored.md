---
slug: phase14-url-catalog-ignored
status: resolved
trigger: |
  Defect C from Phase 14 UAT re-run (2026-05-15): a URL-mode connect call
  with an explicit `?catalog=cerner_src` query parameter is silently ignored
  when an engine for the same Databricks host already exists in the engine
  pool. The cached engine — bound to the *first* catalog encountered for that
  host — is returned instead, and follow-up `list_schemas` returns the
  schemas of the wrong catalog. No error is raised. This violates the
  Phase 14 URL-parity invariant.

  Per chain D → C → A → B. Defect D (host-deterministic connection_id +
  same key used as engine pool key) was diagnosed in
  .planning/debug/phase14-conn-id-determinism.md and is suspected to
  mechanically subsume C. The goal of this session is to confirm whether C
  has any independent code path or whether D's fix would resolve C as a
  side effect.
created: 2026-05-15
updated: 2026-05-15
goal: find_root_cause_only
---

# Debug Session: phase14-url-catalog-ignored

## Symptoms

DATA_START
**Expected behavior:**
- Per Phase 14's URL-parity invariant, a URL-mode `connect_database` call
  with `?catalog=X` should bind the returned engine to catalog X.
- Subsequent `list_schemas(connection_id=...)` should return X's schemas.
- This should hold even if a prior connect for the same host was bound to
  a different catalog Y.

**Actual behavior:**
- Sequence observed during Phase 14 UAT re-run on 2026-05-15:
  1. Named-config connect to `databricks-test` (catalog `bmtct` configured)
     → returns `connection_id: f255ae1dfbb3`, message indicates catalog
     bmtct.
  2. URL-mode connect to same host with `?catalog=cerner_src` →
     returns the SAME `connection_id: f255ae1dfbb3` and a success message
     that still references bmtct (not cerner_src).
  3. `list_schemas(connection_id=f255ae1dfbb3)` returns bmtct's schemas,
     not cerner_src's.
- Catalog override is silently dropped. No error, no warning.

**Errors:** None. Defect is silent.

**Timeline:**
- Surfaced during the Phase 14 UAT re-run after the prior Databricks TLS
  gap stopped reproducing.
- Phase 14 unit tests are green; the defect lives in a runtime path the
  unit tests don't exercise (engine pool reuse with differing URL params).

**Reproduction:**
1. Configure `[connections.databricks-test]` in dbmcp.toml with catalog
   bmtct (or any catalog X).
2. Restart dbmcp server cleanly.
3. `connect_database(connection_name="databricks-test")` — establishes a
   pool entry bound to catalog X.
4. `connect_database(sqlalchemy_url="databricks://...&catalog=cerner_src")`
   — observe identical connection_id, success message still references X.
5. `list_schemas(connection_id=...)` — observe X's schemas, not
   cerner_src's.

**Suspected mechanism (carry-over from Defect D session):**
- `_generate_url_connection_id` (src/db/connection.py:636-643) hashes only
  `backend://host:port/database`. For Databricks URLs, `parsed.database`
  is empty (catalog/http_path/schema live in the URL query string per
  src/db/dialects/databricks.py:118-151), so the connection_id collapses
  to `databricks://<host>:0/`.
- The engine pool `self._engines` is keyed on the same connection_id
  (src/db/connection.py:347-351, 422, 589-592). The reuse short-circuit
  `if connection_id in self._engines` fires BEFORE the new URL's catalog
  reaches `dialect.create_engine(...)`, so the new catalog is never
  applied.

**Open question for this session:**
- Is there any code path between URL ingestion and engine factory call
  where the URL's catalog could (or should) override a cached engine's
  binding? Or is the engine-pool short-circuit the *only* mechanism, in
  which case Defect C is purely a downstream consequence of Defect D and
  fixing D's connection_id/pool-key construction will automatically
  resolve C?

**Likely files:**
- `src/db/connection.py` — `connect_with_url` (URL-mode entry point),
  engine pool reuse logic.
- `src/db/dialects/databricks.py` — URL parsing / catalog extraction;
  whether catalog is even read prior to the pool-reuse check.

**Cross-reference:**
- `.planning/debug/phase14-conn-id-determinism.md` — Defect D session,
  status `root_cause_found`. Cited Resolution section already names
  Defect C as "mechanically explained" by D.
DATA_END

## Current Focus

hypothesis: Defect C has no independent code path. The URL's
  `?catalog=` query param is silently ignored solely because the engine
  pool reuse check (`if connection_id in self._engines`) fires upstream
  of `dialect.create_engine(...)` in `connect_with_url`, so the new
  URL's catalog never reaches the engine factory once any engine for
  that host exists.
test: Trace `connect_with_url` from URL ingestion to engine creation.
  Confirm (a) the order of operations is parse-URL → compute
  connection_id → pool-reuse check → dialect.create_engine, and (b)
  there is no separate catalog-override or rebinding path that runs
  on a cache hit.
expecting: A linear flow in src/db/connection.py around lines 340-425.
  The pool-reuse check returns early on hit; on miss, it falls through
  to dialect.create_engine which receives the URL with its catalog.
status: root_cause_found
result: Hypothesis confirmed in full. The flow in `connect_with_url`
  is strictly linear — parse → ID → pool-reuse short-circuit → engine
  creation. The cache-hit branch returns the cached `Connection`
  immediately and never inspects the new URL's query params. No
  catalog-rebind helper exists anywhere in `src/`. Defect C has no
  independent code path; it is purely a downstream consequence of
  Defect D.

## Evidence

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 327-358
  finding: |
    `connect_with_url` is strictly linear:
      346  parsed_url = make_url(sqlalchemy_url)
      347  connection_id = self._generate_url_connection_id(sqlalchemy_url)
      349  if connection_id in self._engines:
      350      logger.info(f"Reusing existing connection: {connection_id}")
      351      return self._connections[connection_id]
      ...
      355  engine = dialect.create_engine(sqlalchemy_url=..., ...)
    The cache-hit branch returns at line 351 without ever inspecting
    `parsed_url` query params or passing `sqlalchemy_url` anywhere
    downstream. The only consumer of the new URL's catalog is
    `dialect.create_engine` at line 355, which is unreachable on a
    cache hit. Confirms (a) the suspected order of operations and
    (b) the absence of any rebind-on-hit branch.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 359-400
  finding: |
    The post-engine-creation paths (the `except ValueError` /
    `_require_databricks_catalog` enrichment at 362-376, and
    `_register_engine` at 383-393) are all gated behind the
    `dialect.create_engine` call at line 355. None of them runs on
    the cache-hit branch. The catalog-validation path
    (`_require_databricks_catalog`) is reachable only via the
    `except ValueError` from a *fresh* engine creation — i.e. only
    when the pool has no entry for that host yet. On a hit, it is
    bypassed entirely.

- timestamp: 2026-05-15
  type: codebase_search
  pattern: "use catalog | set catalog | rebind | switch.*catalog"
  scope: src/
  finding: |
    Zero matches across `src/`. There is no code path that issues a
    `USE CATALOG` statement against a cached engine, no
    rebind/recreate helper, and no catalog-switch logic. A cached
    engine, once created, is returned verbatim by line 351. This
    rules out the only plausible alternative mechanism — that a hit
    might still apply the new catalog by mutating the cached engine
    or running a per-call session statement.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 503-560
  finding: |
    `_require_databricks_catalog` is the only catalog-related logic
    outside of engine creation in this file, and it is exclusively a
    missing-catalog *error enrichment* helper (builds an accessible-
    catalog listing for the error message). It is invoked only from
    the `except ValueError` handlers in `connect_with_url` (line 368)
    and `_connect_databricks_from_config` (line 606), both of which
    are downstream of the `if connection_id in self._engines`
    short-circuit. It cannot rebind a cached engine and is not
    reachable on a cache hit.

## Eliminated

- hypothesis: A catalog-override path runs on cache hit and re-binds
    the cached engine to the new catalog (e.g. via a session-level
    `USE CATALOG` statement).
  ruled_out_by: Codebase search for `use catalog`, `set catalog`,
    `rebind`, `switch.*catalog` across `src/` returns zero matches.
    The cache-hit branch at connection.py:349-351 returns
    `self._connections[connection_id]` verbatim with no further
    processing.

- hypothesis: The URL is re-parsed inside the cache-hit branch and
    catalog is read from `parsed_url` for some override step before
    return.
  ruled_out_by: Lines 349-351 contain only the `if/log/return`
    triple. `parsed_url` is computed at line 346 but is consumed
    only by `_register_engine` at lines 388-391, which executes on
    the cache-miss branch. On a hit, `parsed_url`'s catalog
    information is computed-and-discarded.

- hypothesis: Defect C has an independent code path distinct from
    Defect D's pool-reuse short-circuit.
  ruled_out_by: Combined evidence from the two `code_inspection`
    findings above and the negative `codebase_search` result. The
    only mechanism by which the new URL's catalog can influence the
    returned engine is via `dialect.create_engine` at line 355,
    which is unreachable whenever `connection_id in self._engines`.
    Therefore C is fully explained by D.

## Resolution

**Root cause:**
Defect C (URL `?catalog=` silently ignored on a cache hit) has **no
independent code path**. It is a strict downstream consequence of
Defect D's coarse connection_id / engine-pool key. The cause-effect
chain is:

1. Defect D: `_generate_url_connection_id` (connection.py:636-643)
   hashes only `backend://host:port/database`, omitting URL query
   params. For Databricks, `parsed.database` is empty, so any two
   URLs that differ only in `?catalog=` produce the same
   connection_id.
2. The engine pool (`self._engines`) is keyed on connection_id
   (connection.py:349, 422). Differing-catalog URLs therefore
   collide on the pool key.
3. `connect_with_url` performs the pool-reuse check at line 349 *
   before* calling `dialect.create_engine` at line 355. On a hit,
   line 351 returns the cached `Connection` verbatim — the new URL
   and its `?catalog=` are never read again.
4. There is no rebind-on-hit, USE-CATALOG, or session-level
   override path anywhere in `src/`. Once cached, an engine's
   catalog binding is immutable for the life of that pool entry.

The "open question" framed in the session header — whether any
catalog-override path between URL ingestion and the engine factory
runs on a cache hit — has been answered negatively on three
independent fronts: linear-flow inspection of `connect_with_url`,
inspection of every `catalog` reference in `connection.py`, and a
codebase-wide search for catalog-rebind primitives.

**Severity & scope:** unchanged from the Defect D session. C is
mechanically subsumed by D. Fixing D — by including catalog (and
http_path) in `_generate_url_connection_id`'s safe_key, or by
decoupling the engine-pool key from the connection_id and making
the pool key fine-grained enough to discriminate distinct catalog
bindings — automatically resolves C as a side effect. No
additional fix is required for C.

**Diagnose-only — no fix applied.** Recommendation for the
remediation effort: treat C as a regression test target rather
than a separate fix. After D's fix lands, write a test that
exercises the exact UAT sequence (named-config connect to
catalog X, then URL-mode connect with `?catalog=Y` to the same
host) and assert that the second call returns a *different*
`connection_id` and that `list_schemas` reflects catalog Y. This
test will pass on D's fix and will guard against regressions on
both defects with a single assertion.
