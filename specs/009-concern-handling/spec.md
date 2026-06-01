# Feature Specification: Concern Handling

> **STATUS: COMPLETE** | Merged: 2026-03-10 | Branch: (GSD milestone v1.1 — archived)

**Origin**: GSD milestone **v1.1** (Phases 3–7). Condensed summary reconstructed on the
return to spec-kit (2026-06-01). Full per-phase detail in the frozen archive at
[`docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md).

## Summary

Systematically clear all **10 concern items** from the v1.0 audit: code quality, test
coverage, connection lifecycle, security hardening, serialization, and external
configuration. An audit-first milestone — the audit defined the scope, each phase closed a
cluster of concerns on a progressively cleaner foundation.

## User Scenarios & Testing

### User Story 1 — Robust, well-covered codebase (P1)

A maintainer can trust that error paths are tested, exceptions are narrowly typed, and there
is no dead code or type-suppression debt.

**Acceptance:** dead `metrics.py` removed; 15 broad `except Exception` blocks narrowed to
specific SQLAlchemy types; all `type: ignore` removed; 70%+ coverage floor enforced in CI.

### User Story 2 — Reliable connection lifecycle (P1)

Azure AD connections survive token expiry and clean up on session end.

**Acceptance:** auth-aware `pool_recycle`, `pool_pre_ping`, and `atexit`/SIGTERM cleanup with
SQLSTATE-based error classification.

### User Story 3 — External configuration (P2)

An operator configures named connections and defaults via a TOML file with env-var credential
resolution.

**Acceptance:** TOML config with named connections, `${VAR}` resolution at connection time,
SP allowlist extensions, and config-driven truncation limits.

## Requirements (all validated — v1.1)

- FR-001 — Dead metrics module removed.
- FR-002 — All broad `except Exception:` blocks replaced with specific types.
- FR-003 — `type: ignore` suppressions in the query module eliminated.
- FR-004 — All source modules at 70%+ coverage with CI enforcement.
- FR-005 — Azure AD token refresh handled via `pool_recycle` + `pool_pre_ping`.
- FR-006 — Connections cleaned up on session end via `atexit`.
- FR-007 — Identifier sanitization validates against database metadata (not regex-only).
- FR-008 — sqlglot pinned with 28 edge-case test fixtures.
- FR-009 — Unified type-handler registry for the serialization pipeline (13 Python types).
- FR-010 — TOML config support for named connections and defaults.

## Success Criteria

- SC-001 — All 10 v1.0 audit concerns closed and verified.
- SC-002 — `_classify_db_error` wired into all 9 MCP tool safety nets.
- SC-003 — Coverage floor enforced via `pyproject.toml` `fail_under` + codecov.
