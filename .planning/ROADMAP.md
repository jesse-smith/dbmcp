# Roadmap: dbmcp

## Milestones

- ✅ **v1.0 TOON Response Format Migration** — Phases 1-2 (shipped 2026-03-05)
- 🚧 **v1.1 Concern Handling** — Phases 3-6 (in progress)

## Phases

<details>
<summary>✅ v1.0 TOON Response Format Migration (Phases 1-2) — SHIPPED 2026-03-05</summary>

- [x] Phase 1: Atomic TOON Migration (3/3 plans) — completed 2026-03-04
- [x] Phase 2: Staleness Guard (2/2 plans) — completed 2026-03-05

</details>

### v1.1 Concern Handling

- [ ] **Phase 3: Code Quality & Test Coverage** - Remove dead code, narrow exceptions, fix type suppressions, and establish 70%+ test coverage
- [ ] **Phase 4: Connection Management** - Handle Azure AD token refresh and clean up connections on session end
- [ ] **Phase 5: Security Hardening** - Validate identifiers against metadata and pin sqlglot with edge case fixtures
- [ ] **Phase 6: Serialization & Configuration** - Unify type conversion pipeline and add TOML config file support

## Phase Details

### Phase 3: Code Quality & Test Coverage
**Goal**: Codebase is honest about its error handling and every module has verified test coverage
**Depends on**: Phase 2 (v1.0 complete)
**Requirements**: QUAL-01, QUAL-02, QUAL-03, TEST-01, TEST-02
**Success Criteria** (what must be TRUE):
  1. `src/metrics.py` no longer exists and no imports reference it anywhere in the codebase
  2. Every `except` block in `src/` catches a specific exception type (no bare `except Exception:` remains outside of top-level MCP tool safety nets)
  3. `src/db/query.py` has zero `# type: ignore` comments and passes `uv run pyright` (or mypy) without suppression
  4. `uv run pytest --cov` reports 70% or higher coverage for every module under `src/`
  5. Coverage reporting is configured in `pyproject.toml` with a baseline that CI can enforce
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Connection Management
**Goal**: Database connections survive long-running sessions and are cleaned up when sessions end
**Depends on**: Phase 3
**Requirements**: CONN-01, CONN-02
**Success Criteria** (what must be TRUE):
  1. An Azure AD-authenticated connection pool automatically discards connections whose tokens have expired (via `pool_recycle` and/or `pool_pre_ping`), so queries after 60+ minutes of idle time succeed without manual reconnection
  2. When the MCP server process exits (normally or via client disconnect), all SQLAlchemy engine connections are disposed and no database connections remain open
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

### Phase 5: Security Hardening
**Goal**: Query validation catches edge cases that the current regex/blocklist approach misses
**Depends on**: Phase 3
**Requirements**: SEC-01, SEC-02
**Success Criteria** (what must be TRUE):
  1. `get_sample_data` and any tool that incorporates user-supplied identifiers validates column/table names against actual database metadata (via `sys.columns` or equivalent) before embedding them in SQL
  2. sqlglot is pinned to `>=29.0.0,<30.0.0` in `pyproject.toml` and a dedicated test fixture file covers malformed SQL, SQL injection attempts, T-SQL-specific syntax, and comment-based obfuscation
  3. All edge case fixtures pass, confirming the pinned sqlglot version handles the project's validation needs
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 6: Serialization & Configuration
**Goal**: Type conversion is centralized and the server supports external configuration
**Depends on**: Phase 3
**Requirements**: INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):
  1. A single type handler registry replaces the separate `_truncate_value()` and `_pre_serialize()` pipelines, with a documented mapping from SQL types to serialization functions and fallback logging for unknown types
  2. The server reads an optional TOML config file (`~/.dbmcp/config.toml` or project-local `dbmcp.toml`) for named connections, default parameters, and SP allowlist extensions
  3. Missing or malformed config files produce a warning log but do not prevent server startup (graceful degradation)
  4. Hardcoded system stored procedures remain non-overridable regardless of config file contents (security invariant preserved)
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases 3 through 6 execute sequentially. Phases 4, 5, and 6 all depend on Phase 3 but are independent of each other.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Atomic TOON Migration | v1.0 | 3/3 | Complete | 2026-03-04 |
| 2. Staleness Guard | v1.0 | 2/2 | Complete | 2026-03-05 |
| 3. Code Quality & Test Coverage | v1.1 | 0/? | Not started | - |
| 4. Connection Management | v1.1 | 0/? | Not started | - |
| 5. Security Hardening | v1.1 | 0/? | Not started | - |
| 6. Serialization & Configuration | v1.1 | 0/? | Not started | - |
