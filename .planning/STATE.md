---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: Databricks identifier fixes
status: planning
stopped_at: Phase 15 context gathered
last_updated: "2026-05-28T20:35:59.583Z"
last_activity: "2026-05-28 - Completed quick task 260528-gsk: Add Databricks ca_bundle config + DBMCP_CA_BUNDLE env-var fallback for corp MITM gateways"
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-06 after v2.0 close)

**Core value:** LLM agents can explore and query databases safely, with validated read-only access, dialect-aware metadata, and clear error reporting.
**Current focus:** v2.0 shipped — next milestone not yet scoped. Use `/gsd-new-milestone` to begin.

## Current Position

Phase: 15
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-28 - Completed quick task 260528-gsk: Add Databricks ca_bundle config + DBMCP_CA_BUNDLE env-var fallback for corp MITM gateways

## Performance Metrics

**Velocity:**

- Total plans completed: 40 (v1.0: 5, v1.1: 11)
- Average duration: ~4 min (v1.1 measured)
- Total execution time: ~1.5 hours (v1.1 measured)

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 3 | 3 | 18min | 6min |
| 4 | 2 | 8min | 4min |
| 5 | 2 | 4min | 2min |
| 6 | 2 | 10min | 5min |
| 7 | 2 | 6min | 3min |
| 08 | 3 | - | - |
| 09 | 2 | - | - |
| 10 | 3 | - | - |
| 11 | 2 | - | - |
| 12 | 2 | - | - |
| 13 | 4 | - | - |
| 13.1 | 4 | - | - |
| 14 | 4 | - | - |

*Updated after each plan completion*
| Phase 12 P01 | 13min | 3 tasks | 9 files |
| Phase 12 P02 | 11min | 3 tasks | 6 files |
| Phase 13 P01 | 4min | 2 tasks | 3 files |
| Phase 13 P02 | 15min | 3 tasks | 3 files |
| Phase 13 P03 | 8 min | 2 tasks | 1 files |
| Phase 13 P04 | 2 min | 1 tasks | 1 files |

## Accumulated Context

### Roadmap Evolution

- Phase 13.1 inserted after Phase 13 (URGENT) — Close v2.0 gap: thread dialect through schema_tools/query_tools entry points (WIRING-01, WIRING-02); fix WIRING-03; fix VALID-01 and VALID-02 issues

### Decisions

See PROJECT.md Key Decisions table for full log.
All v1.1 decisions archived to milestones/v1.1-ROADMAP.md.

- [Phase 12]: Write base SQL in TSQL syntax and transpile via sqlglot for cross-dialect support
- [Phase 12]: isinstance-based type classification with MONEY/SMALLMONEY name fallback
- [Phase 12]: Probe-first-column heuristic for Databricks DESCRIBE EXTENDED fast path
- [Phase 12]: Inspector-first with MSSQL INFORMATION_SCHEMA fallback for PK/FK constraint and table discovery
- [Phase 12]: supports_indexes gating: target_has_index=None when dialect.supports_indexes is False
- Plan 13-02: Kept _mock_inspector_for_pk unrenamed (plan-listed as optional); narrowed test_generic_inspector_constraints to generic-only (databricks returns None for target_has_index); narrowed test_fast_path_skipped_for_non_databricks to (mssql,generic)
- Phase 13 Plan 03: parallel-add TestSharedMetadataBehavior to test_metadata.py; retired 2 duplicate index-gating tests
- [Phase 13]: Coverage floor raised from 70 to 85 (single global knob, ~5pt headroom over 90.64% baseline)

### Pending Todos

- [testing] Add Databricks integration tests for env-var substitution and error wrapping (`.planning/todos/pending/2026-05-05-add-databricks-integration-tests.md`)
- [database] Unify 3-part identifier handling and require Databricks catalog (`.planning/todos/pending/2026-05-08-unify-3-part-identifier-handling-and-require-databricks-cata.md`)
- [database] Cross-dialect ca_bundle support (Option 3) (`.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md`)
- [database] URL-mode probe engine should inherit ca_bundle for IDENT-01 enrichment (`.planning/todos/pending/2026-05-28-url-mode-probe-engine-inherit-ca-bundle-for-ident-01-enrichm.md`)

### Blockers/Concerns

- Azure AD token expiry behavior with `pool_pre_ping` needs live testing (non-blocking; `pool_recycle` is primary defense)
- FastMCP has no session-level lifecycle hooks; `atexit` is the cleanup mechanism
- databricks-sqlalchemy Inspector may raise non-SQLAlchemy exceptions (research flag for Phase 11)
- sqlglot transpilation coverage for analysis query patterns needs empirical validation (research flag for Phase 12)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260428-fr7 | Surface config parse failures to the MCP client | 2026-04-28 | fd48be3 | [260428-fr7-surface-config-parse-failures-to-the-mcp](./quick/260428-fr7-surface-config-parse-failures-to-the-mcp/) |
| 260428-jr7 | Fix Databricks connect_with_config (env vars + dialect signature) | 2026-04-28 | 4fdaa90 | [260428-jr7-fix-databricks-connect-with-config-integ](./quick/260428-jr7-fix-databricks-connect-with-config-integ/) |
| 260428-l6x | Fix Databricks Test 7 bugs (validator, table_exists catalog, list_schemas counts + no-catalog) | 2026-04-28 | f651c2b,16c62c3,1c07dfd | [260428-l6x-fix-databricks-test7-bugs](./quick/260428-l6x-fix-databricks-test7-bugs/) |
| 260428-mwr | Fix execute_query row materialization + cross-catalog column fetch | 2026-04-28 | 6d37227,3abcbc1 | [260428-mwr-fix-bugs-just-surfaced-and-listed-in-tod](./quick/260428-mwr-fix-bugs-just-surfaced-and-listed-in-tod/) |
| 260504-ilw | Centralize log file to ~/.dbmcp/logs/ with rotation and auto-migration | 2026-05-05 | afe9b72 | [260504-ilw-centralize-log-file-to-dbmcp-logs-with-r](./quick/260504-ilw-centralize-log-file-to-dbmcp-logs-with-r/) |
| 260505-mhm | Fix connect_with_url to work with MSSQL (MSSQLDialect parses sqlalchemy_url) | 2026-05-05 | c07b071,77721ca,de838d9 | [260505-mhm-fix-connect-with-url-to-work-with-mssql-](./quick/260505-mhm-fix-connect-with-url-to-work-with-mssql-/) |
| 260505-mr3 | Audit Databricks test coverage — verdict: not a blocker; follow-up todo filed for integration tests | 2026-05-05 | (audit-only, no code) | [260505-mr3-audit-test-coverage-for-databricks-conne](./quick/260505-mr3-audit-test-coverage-for-databricks-conne/) |
| 260505-mxi | Drop "Unexpected error:" prefix on ImportError/ModuleNotFoundError in MCP tools | 2026-05-05 | 0859b53,02df7e0,4afd68f | [260505-mxi-drop-unexpected-error-prefix-on-importer](./quick/260505-mxi-drop-unexpected-error-prefix-on-importer/) |
| 260505-o1k | Fix MSSQL driver override — URL-supplied driver query param wins over dialect default | 2026-05-05 | 40358bc,bcc3360 | [260505-o1k-fix-mssql-driver-override-url-supplied-d](./quick/260505-o1k-fix-mssql-driver-override-url-supplied-d/) |
| 260505-o6n | Fix DatabricksDialect URL parsing (parse sqlalchemy_url via make_url — mirrors MSSQL fix) | 2026-05-05 | b50268f,10e56a6 | [260505-o6n-fix-databricksdialect-url-parsing-parse-](./quick/260505-o6n-fix-databricksdialect-url-parsing-parse-/) |
| 260505-own | Apply connect_timeout default (30s) + retry cap (2) to DatabricksDialect — fail-fast on bad hosts | 2026-05-05 | 7b69fb9,ca7e115 | [260505-own-apply-connect-timeout-default-retry-cap-](./quick/260505-own-apply-connect-timeout-default-retry-cap-/) |
| 260506-n8s | Fix dialect-blind SQL generation in QueryService sample-query methods | 2026-05-06 | 888ff20,3d75e42,e4b0d52 | [260506-n8s-fix-dialect-blind-sql-generation-in-quer](./quick/260506-n8s-fix-dialect-blind-sql-generation-in-quer/) |
| 260507-e8m | Fix all 8 complexity violations flagged by CI complexipy gate | 2026-05-07 | f026ca0,2e7b1b9,a3117be,7fc0531,2e1559e,de8e433,be992eb,6bbc680,76bc6c1 | [260507-e8m-fix-all-8-complexity-violations](./quick/260507-e8m-fix-all-8-complexity-violations/) |
| 260507-h6j | Move all optional extras to hard dependencies | 2026-05-07 | 4548866 | [260507-h6j-move-all-optional-extras-to-hard-depende](./quick/260507-h6j-move-all-optional-extras-to-hard-depende/) |
| 260515-m30 | Draft C/D fixes — Databricks connection_id collision across catalogs | 2026-05-15 | bc2244f | [260515-m30-draft-c-d-fixes](./quick/260515-m30-draft-c-d-fixes/) |
| 260528-fks | Fix Defect A — Databricks catalog defaults bypass IDENT-01 | 2026-05-28 | 72f26f8 | [260528-fks-fix-defect-a-databricks-catalog-defaults](./quick/260528-fks-fix-defect-a-databricks-catalog-defaults/) |
| 260528-gsk | Add Databricks ca_bundle config + DBMCP_CA_BUNDLE env-var fallback for corp MITM gateways | 2026-05-28 | 269a6da | [260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca](./quick/260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca/) |
| fast (2026-05-28) | Resolve `${VAR}` in `sqlalchemy_url` for URL-mode connect (closes URL-mode env-var gap from 260515-m30 Probe 3) | 2026-05-28 | 43fed65 | (inline /gsd:fast — no directory) |

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 15 context gathered
Resume file: --resume-file

**Planned Phase:** 14 (connect-time-hardening-databricks) — 4 plans — 2026-05-11T20:50:13.408Z
