---
phase: 06-serialization-configuration
plan: 02
subsystem: infra
tags: [toml, config, named-connections, sp-allowlist, env-vars]

requires:
  - phase: 06-serialization-configuration/01
    provides: TOON serialization format used by all tools
provides:
  - TOML config file support (dbmcp.toml / ~/.dbmcp/config.toml)
  - Named database connections with config precedence
  - Configurable defaults (query_timeout, text_truncation_limit, sample_size, row_limit)
  - Additive SP allowlist merging with hardcoded system SPs
  - ${VAR} env var resolution for credentials at connection time
affects: [all-tools, server-startup, connection-management]

tech-stack:
  added: [tomllib]
  patterns: [frozen-dataclass-config, module-singleton, deferred-env-var-resolution]

key-files:
  created: [src/config.py, tests/unit/test_config.py]
  modified: [src/mcp_server/server.py, src/mcp_server/schema_tools.py, src/mcp_server/query_tools.py, src/db/validation.py]

key-decisions:
  - "Env vars resolved at connection time, not load time, for security and flexibility"
  - "SP name validation uses ^[a-zA-Z_][\\w.]*$ to allow schema-qualified names while rejecting injection"
  - "Config file precedence: local dbmcp.toml > ~/.dbmcp/config.toml > hardcoded defaults"
  - "Tool arg precedence: explicit args > named connection config > hardcoded defaults"

patterns-established:
  - "Frozen dataclass config: all config types are immutable after creation"
  - "Module singleton: init_config() at startup, get_config() everywhere else"
  - "Deferred resolution: credentials stay as ${VAR} strings until connection time"

requirements-completed: [INFRA-02]

duration: 6min
completed: 2026-03-10
---

# Phase 06 Plan 02: Config File Support Summary

**TOML config file support with named connections, configurable defaults, SP allowlist extensions, and ${VAR} credential resolution**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-10T17:54:54Z
- **Completed:** 2026-03-10T18:01:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Config module with frozen dataclass hierarchy (AppConfig/DefaultsConfig/ConnectionConfig)
- Named connection support in connect_database with full precedence chain
- Configurable query defaults (sample_size, row_limit) with validated bounds
- SP allowlist merges additively -- hardcoded system SPs cannot be removed via config
- 32 new unit tests covering all config behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1: Create config.py with TOML loading, validation, and tests** - `c3d6cc1` (feat, TDD)
2. **Task 2: Integrate config into server, tools, and SP allowlist** - `3ac1d5e` (feat)

## Files Created/Modified
- `src/config.py` - TOML config loading, validation, env var resolution, module singleton
- `tests/unit/test_config.py` - 32 tests for config module
- `src/mcp_server/server.py` - init_config() call at startup
- `src/mcp_server/schema_tools.py` - connection_name parameter with config precedence
- `src/mcp_server/query_tools.py` - sample_size and row_limit use config defaults
- `src/db/validation.py` - get_allowed_procedures() merges config SP allowlist

## Decisions Made
- Env vars resolved at connection time (not load time) for security -- credentials don't linger in memory as plaintext
- SP names validated with `^[a-zA-Z_][\w.]*$` to support schema-qualified names (dbo.my_proc) while rejecting injection patterns
- Tool argument precedence: explicit args > named connection config > hardcoded defaults
- Config file search order: ./dbmcp.toml > ~/.dbmcp/config.toml

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TOML test SP placement**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Test TOML placed `allowed_stored_procedures` after a `[connections.prod]` table header, causing TOML to nest it under connections instead of root
- **Fix:** Moved SP list before section headers in test TOML
- **Files modified:** tests/unit/test_config.py
- **Verification:** All 32 tests pass
- **Committed in:** c3d6cc1 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test data fix only, no scope creep.

## Issues Encountered
- Pre-existing Azure AD credential expiry in tests/integration/test_azure_ad_auth.py (not caused by these changes, expired credentials need `az login` refresh)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Config infrastructure complete, ready for any future features that need configuration
- Named connections enable multi-database workflows
- SP allowlist extensibility enables customer-specific stored procedure access

---
*Phase: 06-serialization-configuration*
*Completed: 2026-03-10*
