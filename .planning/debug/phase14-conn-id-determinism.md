---
slug: phase14-conn-id-determinism
status: resolved
trigger: |
  Defect D from Phase 14 UAT re-run (2026-05-15): connection_id appears
  host-deterministic — same ID returned across many distinct connect calls,
  including across full server restarts and across calls with different
  catalog URL parameters. Suspected to be the underlying mechanism enabling
  Defects C (URL catalog ignored) and A (catalog requirement bypassed).
  Diagnose D first because it blocks observability into the others.
created: 2026-05-15
updated: 2026-05-15
goal: find_root_cause_only
---

# Debug Session: phase14-conn-id-determinism

## Symptoms

DATA_START
**Expected behavior:**
- `connection_id` returned by `connect_database` should uniquely identify a
  live SQLAlchemy engine that the client can use for follow-up MCP calls.
- Two `connect_database` calls that should produce *different* engines (e.g.
  same host but different catalog binding, or after a full server-process
  restart) should not share a `connection_id`.
- Per Phase 14's URL-parity invariant, a URL with `?catalog=X` should bind
  the engine to catalog X.

**Actual behavior:**
- `connection_id: f255ae1dfbb3` is returned across:
  - Named-config connect (with `catalog = "bmtct"` in dbmcp.toml)
  - Named-config connect (with catalog commented out in dbmcp.toml)
  - URL-mode connect with `?catalog=bmtct`
  - URL-mode connect with `?catalog=cerner_src` (still returned bmtct's
    schemas — catalog override silently ignored)
  - URL-mode connect with no `?catalog=` at all
  - Calls after `/mcp` reconnect (client transport reset, server kept)
  - Calls after a **full Claude Code session restart** that should have
    spawned a fresh dbmcp server process

**Errors:**
- None. Behavior is silent. `status: success` returned in all cases that
  should arguably have failed (Defect A) or produced a different engine
  (Defect C).

**Timeline:**
- Surfaced 2026-05-15 during the Phase 14 UAT re-run after the prior
  Databricks TLS gap stopped reproducing.
- Phase 14 unit tests are green (`test_metadata.py:771` etc.) — defect lives
  in a runtime path the unit tests don't exercise.

**Reproduction:**
1. Configure `[connections.databricks-test]` in dbmcp.toml (project root)
   with host/http_path/token; catalog optional.
2. Restart dbmcp server (full Claude Code restart, not `/mcp` reconnect).
3. Call `connect_database(connection_name="databricks-test")` — note
   `connection_id`.
4. Call `connect_database(sqlalchemy_url="databricks://...&catalog=cerner_src")`
   — observe identical `connection_id` and "connected to bmtct" message.
5. Call `list_schemas(connection_id=...)` — observe schemas of the
   first-bound catalog, not the URL-requested one.

**Suspected mechanism:**
- `connection_id` is computed as a hash of `(host, http_path)` only, with
  catalog and other engine-identifying params excluded.
- The engine pool likely uses the same coarse key for dedup, which is why
  URL `?catalog=` is ignored once any engine for that host exists.
- Determinism across server restart suggests it's a pure function of the
  config inputs, not a runtime-allocated identifier — so the same hash
  collides with whatever was previously created and may even refer to a
  stale engine after restart.

**Likely files:**
- `src/dbmcp/connection.py` — `connect_with_url`, `connect_with_config`,
  engine pool / connection_id generation.
- `src/dbmcp/dialects/databricks.py` — URL parsing, catalog handling.
DATA_END

## Current Focus

hypothesis: connection_id is computed as hash(host, http_path) only,
  excluding catalog and other engine-identifying parameters; engine pool
  shares the same coarse key, causing URL `?catalog=` to be silently
  ignored when an engine for the host already exists.
test: Locate the connection_id generation site and the engine pool key
  construction. Confirm catalog is excluded from both.
expecting: A hash function over a tuple/string that does not include
  catalog. Likely in `src/dbmcp/connection.py`.
status: root_cause_found
result: Hypothesis confirmed in shape but refined in detail.
  - Actual safe_key shape is hash(backend, host, port, database) — NOT
    (host, http_path). http_path is also excluded; correlation with host
    is incidental because http_path tends to co-vary with host.
  - For Databricks URLs `parsed.database` is empty (catalog/http_path/schema
    live in the URL query string, not the URL path), so the safe_key
    collapses to `databricks://<host>:0/`.
  - Engine pool dedup uses the same connection_id as its dict key
    (`self._engines[connection_id]`), so the pool key IS the connection_id
    — single coarse signature for both, as suspected.

## Evidence

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 636-643
  finding: |
    `_generate_url_connection_id` builds the safe_key from
    `parsed.get_backend_name()`, `parsed.host`, `parsed.port`, and
    `parsed.database` only:

        safe_key = f"{parsed.get_backend_name()}://{parsed.host or ''}:{parsed.port or 0}/{parsed.database or ''}"
        return hashlib.sha256(safe_key.encode()).hexdigest()[:CONNECTION_ID_LENGTH]

    Query parameters (`http_path`, `catalog`, `schema`) are not in the key.
    This is the URL-mode generator.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/dialects/databricks.py
  lines: 118-151
  finding: |
    Databricks URLs encode catalog/http_path/schema in the URL query string,
    not the path:
      - http_path  ← url.query["http_path"]
      - catalog    ← url.query.get("catalog", "")
      - schema     ← url.database or url.query.get("schema") or "default"
    `parsed.database` is therefore typically empty for Databricks. Combined
    with line 642 of connection.py, the safe_key collapses to
    `databricks://<host>:0/` — pure host-determinism, exactly matching the
    UAT observation that one host produced one ID across all catalog
    variants.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 563-592
  finding: |
    `_connect_databricks_from_config` (named-config Databricks path) builds
    a `canonical_url` of the form
      databricks://token:...@{host}?http_path=...&catalog=...&schema=...
    and feeds it to `_generate_url_connection_id` (line 589). Because the
    generator only hashes host/port/database, the `?catalog=` and
    `?http_path=` discriminators in the canonical_url are silently dropped
    from the connection_id. Two configs that differ only in `catalog` will
    collide.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 347-351, 422, 589-592
  finding: |
    The engine pool is `self._engines: dict[str, Engine]` keyed by
    `connection_id`. Both `connect_with_url` (line 347-351) and
    `_connect_databricks_from_config` (line 589-592) check
    `if connection_id in self._engines` and short-circuit to return the
    cached `self._connections[connection_id]`. Registration at line 422
    writes `self._engines[connection_id] = engine`. The pool dedup key is
    therefore identical to the connection_id — a single coarse signature
    governs both ID generation AND engine reuse. This confirms the second
    half of the hypothesis.

- timestamp: 2026-05-15
  type: code_inspection
  file: src/db/connection.py
  lines: 281-309
  finding: |
    The non-Databricks named-config path (`_generate_connection_id`) hashes
    `{server}:{port}/{database}/{user_component}` — for SQL Server
    connections `database` is the actual database name, so collisions are
    less severe there. This path does not feed the Databricks reproduction;
    Databricks goes through the URL-style generator (line 589). Noted to
    bound the scope of the defect: SQL Server connections are NOT impacted
    (they include database in the key); Databricks is, because for
    Databricks URLs `parsed.database` is empty.

- timestamp: 2026-05-15
  type: cross_session_persistence_analysis
  finding: |
    Determinism across full server-process restart (UAT step where Claude
    Code session was fully restarted) is consistent with the safe_key being
    a pure function of input config values. The hash itself is stable; the
    `_engines` dict is process-local (a fresh server has an empty dict on
    line 144), so the post-restart "reuse" the user observed is in fact a
    fresh registration that happens to receive the same deterministic ID.
    Implication: there is no stale-engine hazard from determinism per se;
    the real hazards are (a) within-process catalog-collision (Defects C/A)
    and (b) UX confusion ("same ID across restart looks like a leak").

## Eliminated

- hypothesis: connection_id is a UUID or runtime-allocated token
  ruled_out_by: Line 643 — explicit `hashlib.sha256(safe_key.encode())`. No
    randomness, no time component, no per-process salt.

- hypothesis: catalog IS in the key but is being normalized away (e.g.
    lowercased to empty) before hashing
  ruled_out_by: Line 642 reads only `parsed.host`, `parsed.port`,
    `parsed.database`. Catalog is never read by the generator at all.

- hypothesis: SQL Server connections share this defect
  ruled_out_by: The non-Databricks path uses `_generate_connection_id`
    (line 281) which DOES include `database` in the key. SQL Server's
    database lives in the URL path, so it propagates correctly. Defect is
    Databricks-specific because Databricks URLs route catalog through
    query-string params that the generic URL hasher ignores.

## Resolution

**Root cause:**
`_generate_url_connection_id` (src/db/connection.py:636-643) hashes only
`backend://host:port/database` — it never inspects URL query parameters.
For Databricks URLs the catalog/http_path/schema discriminators all live in
the query string and `parsed.database` is empty, so every Databricks
connect call against a given host collapses to the same `connection_id`.
The engine pool (`self._engines`) is keyed on this same connection_id at
src/db/connection.py:349, 422, 590, so the first engine created for a host
permanently wins: any subsequent `connect_database` call against that host
short-circuits at the `if connection_id in self._engines` reuse check
(lines 349-351, 590-592) and returns the cached engine — silently
discarding the new URL's catalog binding.

**Severity:** HIGH for Databricks. The defect is silent (no error raised),
violates the documented URL-parity invariant, and produces wrong-catalog
query results for any user who reconnects with a different `?catalog=`
within the same server process.

**Scope of impact:**
- **Defect D (this one):** mechanically explained — catalog and query
  params are absent from both the ID hash and the pool key.
- **Defect C (URL `?catalog=` silently ignored):** mechanically explained.
  Once any engine exists for the host, the reuse check at line 349-351 (or
  590-592 for config mode) fires before `dialect.create_engine(...)` is
  called with the new catalog. The new URL's catalog never reaches the
  engine factory; the cached engine bound to the *first* catalog is
  returned instead.
- **Defect A (catalog requirement bypass):** mechanically explained. The
  catalog-required validation lives inside `dialect.create_engine` and the
  `_require_databricks_catalog` enrichment at line 606. Both are downstream
  of the reuse check. If a prior call (with catalog) populated the pool,
  a later call (without catalog) hits the `connection_id in self._engines`
  branch and returns the cached engine without ever entering the validation
  path that would have raised.
- **Defect B:** not analyzed in this session (out of scope per user
  ordering D → C → A → B).
- **SQL Server (mssql):** NOT impacted — its named-config path uses
  `_generate_connection_id` which includes `database`, and its URL form
  carries the database in the URL path so `parsed.database` is non-empty.

**Diagnose-only — no fix applied.** Remediation directions for the user to
consider (not implemented):
1. Include URL query params (or at minimum `catalog` and `http_path`) in
   the safe_key construction at connection.py:642.
2. Decouple connection_id from the engine pool key, OR keep them coupled
   but ensure the key is fine-grained enough to discriminate every binding
   that produces a behaviorally distinct engine.
3. Consider whether reuse semantics should be "same host, same catalog →
   reuse" or "always fresh engine, ID just identifies the binding" — these
   imply different fixes.
