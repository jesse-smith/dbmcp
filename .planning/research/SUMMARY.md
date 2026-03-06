# Project Research Summary

**Project:** dbmcp v1.1 Concern Handling
**Domain:** Internal quality improvements for Python MCP database server (SQLAlchemy + pyodbc + SQL Server)
**Researched:** 2026-03-06
**Confidence:** HIGH

## Executive Summary

The dbmcp v1.1 milestone is a hardening and internal quality pass on an existing, working MCP server with 9 tools and 506 tests. The codebase has accumulated 25 broad `except Exception` blocks, a dead metrics module, duplicated type-conversion pipelines, no configuration file, and an Azure AD token refresh gap that causes silent failures after 60-90 minutes of idle time. None of these concerns require new dependencies -- the entire milestone is achievable with stdlib additions (`tomllib`, `time`, `uuid`) and better use of existing libraries (`sqlalchemy.exc`, `sqlalchemy.event`, `azure.core.credentials.AccessToken`).

The recommended approach is cleanup-first: remove dead code, narrow exception handling, and fix type ignore smells before adding new capabilities. This ordering is critical because writing tests against code you plan to refactor wastes effort, and narrowing exceptions changes error messages that existing tests assert on. The identifier validation and type handler registry introduce cross-module coupling changes that are easier to reason about once exception flows are clean. The config file and Azure AD token lifecycle changes are infrastructure that benefits from a stable foundation.

The primary risks are (1) cascading test failures from error message changes when narrowing exceptions (30+ tests assert on error message content), (2) Azure AD token expiry on pooled connections that only manifests in long-running production sessions, and (3) the type handler registry conflicting with the existing dual type-conversion pipeline. All three are well-understood and have clear prevention strategies documented in the pitfalls research. The zero-new-dependencies constraint eliminates supply chain risk entirely.

## Key Findings

### Recommended Stack

No new dependencies are required. The entire v1.1 milestone uses existing libraries and stdlib modules. See [STACK.md](STACK.md) for full details.

**Core technologies (no changes):**
- **SQLAlchemy 2.0.47** (`sqlalchemy.exc` for specific exceptions, `sqlalchemy.event` for pool checkout listener) -- already installed
- **azure-identity 1.25.2** (`AccessToken.expires_on` for token expiry tracking) -- already installed
- **tomllib** (stdlib since Python 3.11) -- config file parsing with zero new dependencies

**One dependency change:**
- **sqlglot**: tighten from `>=26.0.0,<30.0.0` to `>=29.0.0,<30.0.0` -- codebase uses v29+ expression types (`exp.Execute`, `exp.ExecuteSql`)

### Expected Features

See [FEATURES.md](FEATURES.md) for full analysis with complexity estimates.

**Must have (table stakes):**
- Specific exception handling (25 broad catches hide real bugs)
- Dead code removal (metrics.py has zero consumers)
- Type ignore cleanup (monkey-patched attributes on Query dataclass)
- MCP session cleanup (connections leak on client disconnect)
- Test coverage to 70% per module (validates all changes)

**Should have (differentiators):**
- Azure AD token refresh in connection pool (prevents silent auth failures after 60-90 min)
- Type handler registry (eliminates duplicated isinstance chains, handles uuid.UUID and bytes)
- Configuration file (TOML, enables SP allowlist customization and pool tuning)
- sqlglot version pinning with edge case test fixtures

**Defer (v2+):**
- SQL identifier validation against metadata (moderate coupling change, needs QueryService refactor)
- Pydantic migration (explicitly out of scope per PROJECT.md)
- Query result caching, audit logging (explicitly out of scope)

### Architecture Approach

The existing architecture is sound: FastMCP entry point, async tool handlers wrapping sync service layer via `asyncio.to_thread`, SQLAlchemy engine pool, TOON serialization. Changes are internal quality improvements that do not alter the component boundaries or request flow. See [ARCHITECTURE.md](ARCHITECTURE.md) for full component map.

**New components:**
1. **Config loader** (`src/config.py`) -- TOML parsing, validation, defaults; loaded lazily in `main()`, not at import time
2. **Type handler registry** (extend `src/serialization.py` or new `src/type_handlers.py`) -- centralized type-to-serializer mapping replacing dual isinstance chains

**Modified components (exception narrowing):**
3. **metadata.py** -- 10+ broad catches narrowed to `sqlalchemy.exc.OperationalError`, `ProgrammingError`, `NoSuchTableError`
4. **MCP tool handlers** -- layered catches: specific DB errors first, `Exception` retained as final safety net
5. **connection.py / azure_auth.py** -- pool checkout event for token expiry, `atexit` handler for cleanup

**Removed components:**
6. **metrics.py** -- zero imports, zero usage, safe to delete

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for all 12 pitfalls with detailed prevention strategies.

1. **Error message assertion drift** -- Narrowing exceptions changes `type(e).__name__` in error messages; 30+ tests assert on these strings. Mitigation: audit test assertions first, change one module at a time, keep tool-layer catch-all.
2. **Azure AD token expiry on pooled connections** -- `pool_pre_ping` may not detect expired tokens (error code not recognized as disconnect). Mitigation: set `pool_recycle=1800` (under 60-min token lifetime), add `checkout` event listener, cache `AccessToken.expires_on`.
3. **Type handler registry triple-conversion** -- Adding a registry alongside existing `_truncate_value` and `_pre_serialize` creates three conversion layers. Mitigation: make registry additive for new types first; map existing type flow end-to-end before unifying.
4. **Config file startup failure** -- Malformed config at import time crashes the server silently. Mitigation: config is optional, load lazily in `main()`, never fail on missing file.
5. **SP allowlist security bypass** -- User-editable config could add `xp_cmdshell` to allowlist. Mitigation: hardcoded system SPs are non-overridable base; maintain explicit denylist of dangerous procedures.

## Implications for Roadmap

Based on combined research, the work groups into four phases with clear dependency ordering.

### Phase 1: Cleanup and Safety Net

**Rationale:** Refactoring must happen before test writing. Dead code and broad exceptions create noise that obscures real issues. This phase has zero new features -- it makes the existing codebase honest about its error handling.

**Delivers:** Clean exception hierarchy, no dead code, proper QueryResult type, session cleanup via atexit.

**Addresses features:** Dead code removal, exception specificity, type ignore cleanup, MCP session cleanup.

**Avoids pitfalls:** Error message assertion drift (Pitfall 2) by auditing test assertions first and changing one module at a time. Metrics removal safety (Pitfall 1) by searching all file types. Session cleanup scope (Pitfall 10) by using atexit, not session events.

**Estimated scope:** ~200-250 lines changed across 8 files; ~15-25 test assertion updates.

### Phase 2: Validation and Testing

**Rationale:** Tests should cover the final code shape, not pre-refactored code. This phase proves Phase 1 changes are correct and adds regression protection. sqlglot pinning and edge case fixtures belong here because they are test-focused.

**Delivers:** 70%+ coverage per module, sqlglot pinned to v29 with edge case fixtures, validated error recovery paths.

**Addresses features:** Test coverage to 70%, sqlglot version pinning + fixtures.

**Avoids pitfalls:** Hollow test coverage (Pitfall 9) by focusing on behavioral coverage of error/exception paths. Version-locked fixtures (Pitfall 8) by testing at SQL level, not AST level.

**Estimated scope:** ~400-600 lines of new tests; pyproject.toml version pin change.

### Phase 3: Infrastructure Additions

**Rationale:** New capabilities layered on a clean, well-tested foundation. Config file enables future customization. Type handler registry eliminates duplication. Azure AD token refresh prevents production failures. These are independent of each other but all benefit from clean exception handling.

**Delivers:** TOML config file support, type handler registry, Azure AD token proactive refresh.

**Addresses features:** Configuration file, type handler registry, Azure AD token refresh.

**Avoids pitfalls:** Config startup failure (Pitfall 6) with lazy loading and optional config. SP allowlist bypass (Pitfall 7) with non-overridable base + denylist. Triple-conversion conflict (Pitfall 5) by making registry additive. Token expiry (Pitfall 3) with pool_recycle + checkout event.

**Estimated scope:** ~250-350 lines across 5 files; 2 new modules (config.py, type_handlers.py or extension of serialization.py).

### Phase 4 (Stretch): Identifier Validation

**Rationale:** Deferred because it requires threading MetadataService into QueryService, which is a coupling change that benefits from stable foundations. Lower urgency -- the existing bracket-quoting prevents injection; this adds correctness.

**Delivers:** Metadata-validated identifiers in get_sample_data, support for special-character column names.

**Addresses features:** SQL identifier validation against metadata.

**Avoids pitfalls:** Over-restrictive validation (Pitfall 4) by validating against DB metadata, not regex patterns.

**Estimated scope:** ~50-80 lines in query.py + metadata.py; test fixtures with adversarial column names.

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** Refactoring before testing prevents test-rewrite churn. Exception narrowing changes error messages that tests assert on -- doing both simultaneously doubles the debugging effort.
- **Phase 2 before Phase 3:** Tests provide a safety net for the infrastructure additions. Config loading, type registry, and pool event changes are all testable changes that should have coverage.
- **Phase 3 items are independent:** Config file, type registry, and Azure AD refresh can be developed in any order within the phase. They share no code dependencies.
- **Phase 4 is optional for v1.1:** Identifier validation is the only feature requiring cross-service coupling changes. It can slip to v1.2 without impacting the milestone goals.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Azure AD token refresh):** The interaction between `pool_pre_ping`, `checkout` events, and Azure AD error codes needs integration testing against a real Azure AD connection. Unit tests with mocked tokens can validate the logic, but the error code recognition gap (Pitfall 3) can only be confirmed with a live Azure environment.
- **Phase 4 (Identifier validation):** The MetadataService integration into QueryService needs design decisions about caching (should metadata be fetched per-query or cached per-session?).

Phases with standard patterns (skip deeper research):
- **Phase 1 (Cleanup):** Exception narrowing is mechanical -- the specific exception types are documented in STACK.md with verified imports. Dead code removal is trivially safe.
- **Phase 2 (Testing):** Standard pytest patterns. The test suite structure is well-established.
- **Phase 3 (Config file and type registry):** TOML loading via tomllib is stdlib and well-documented. Type registry is a standard Python pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All findings verified against installed versions; zero new dependencies |
| Features | HIGH | Based on direct codebase analysis of all src/ modules and PROJECT.md constraints |
| Architecture | HIGH | Component map verified by reading every source file; request flow traced end-to-end |
| Pitfalls | HIGH | All 12 pitfalls grounded in specific code locations with line-level evidence; 506-test suite inspected for assertion patterns |

**Overall confidence:** HIGH

All four research outputs are based on direct codebase inspection rather than external documentation or inference. The codebase is small enough (11 source modules, 506 tests) that exhaustive analysis was feasible.

### Gaps to Address

- **Azure AD token error code behavior:** Whether `pool_pre_ping` detects expired Azure AD tokens depends on how SQL Server reports the error and whether SQLAlchemy's `is_disconnect()` recognizes that error code. This needs live testing against an Azure AD-authenticated SQL Server instance. Workaround: `pool_recycle` as primary defense makes this gap non-blocking.
- **FastMCP lifecycle hooks:** STACK.md and PITFALLS.md both note that FastMCP does not expose session-level disconnect hooks. The `atexit` approach is confirmed to work for process-lifetime cleanup. If FastMCP adds lifecycle hooks in a future release, the cleanup strategy could be refined.
- **sqlglot v30 migration path:** Pinning to `>=29.0.0,<30.0.0` is correct for now, but sqlglot does not follow semver. When v30 releases, the dual-path handling (Execute vs Command) may need a third path. The edge case test fixtures in Phase 2 will serve as upgrade canaries.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all 11 source modules in `src/`
- SQLAlchemy 2.0.47 exception hierarchy and pool events (verified via introspection)
- pyodbc 5.3.0 exception hierarchy (verified via runtime inspection)
- azure-identity `AccessToken` NamedTuple (verified: `token: str, expires_on: int`)
- Python 3.13.1 `tomllib` stdlib availability (verified in runtime)
- sqlglot 29.0.1 expression types (verified: Execute, ExecuteSql, Kill, IfBlock, WhileBlock all present)
- Test suite: 506 tests, 30+ error message assertions identified

### Secondary (MEDIUM confidence)
- Azure AD token lifetime (~60-90 minutes) -- from Microsoft identity platform documentation
- FastMCP lifecycle capabilities -- verified via introspection; no shutdown hook, use `atexit`

### Tertiary (LOW confidence)
- `pool_pre_ping` interaction with Azure AD token expiry error codes -- needs live integration testing

---
*Research completed: 2026-03-06*
*Ready for roadmap: yes*
