# Tasks: Concern Handling

> **STATUS: COMPLETE** | Merged: 2026-03-10 | Branch: (GSD milestone v1.1 — archived)

**Origin**: GSD milestone **v1.1**, 5 phases / 11 plans / 22 tasks, all complete.
Condensed checklist; per-plan detail in
[`docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md).

## Phase 3 — Code Quality & Test Coverage (3 plans)

- [X] Delete dead `metrics.py`; narrow 15 broad exceptions to specific SQLAlchemy types; remove all `type: ignore`.
- [X] Add 9 error-path tests; enforce 70% coverage floor via `pyproject.toml` `fail_under` + `codecov.yml`.

## Phase 4 — Connection Management (2 plans)

- [X] Auth-aware `pool_recycle=2700` + `pool_pre_ping` for Azure AD connections.
- [X] `atexit`/SIGTERM lifecycle cleanup with SQLSTATE-based error classification.

## Phase 5 — Security Hardening (2 plans)

- [X] Metadata-based column validation replacing regex-only sanitization (fail-open fallback).
- [X] Pin sqlglot; add 28 parametrized edge-case tests.

## Phase 6 — Serialization & Configuration (2 plans)

- [X] Unified type-handler registry (13 Python types) replacing duplicate `_pre_serialize`/`_truncate_value`.
- [X] TOML config: named connections, `${VAR}` credential resolution, SP allowlist extensions, config-driven truncation.

## Phase 7 — Wire Orphaned Exports (2 plans)

- [X] Wire `_classify_db_error` into all 9 MCP tool safety nets.
- [X] Close the two integration gaps found by the gap-closure audit (would have shipped as dead code).

**Outcome:** all 10 v1.0 audit concerns closed; 682 tests; 70%+ floor; 11 plans over 5 days.
