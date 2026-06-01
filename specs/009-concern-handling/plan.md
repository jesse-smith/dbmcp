# Implementation Plan: Concern Handling

> **STATUS: COMPLETE** | Merged: 2026-03-10 | Branch: (GSD milestone v1.1 — archived)

**Origin**: GSD milestone **v1.1** (Phases 3–7, 11 plans, shipped 2026-03-10).
Condensed summary; full detail in
[`docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v1.1-ROADMAP.md).

## Summary

Audit-first milestone clearing 10 concerns from the v1.0 audit. Phase ordering
(cleanup → tests → features) meant each phase built on a cleaner foundation; Phases 4/5/6
were mutually independent (all depended only on Phase 3), enabling clean sequential
execution. A final gap-closure phase (Phase 7) wired two orphaned exports that would
otherwise have shipped as dead code.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: existing stack + tomllib (stdlib), sqlglot (pinned)
**Project Type**: MCP server
**Constraints**: 70%+ coverage floor; read-only; metadata-based identifier validation.

## Phases

- **Phase 3 — Code Quality & Test Coverage** (3 plans): remove dead code, narrow exceptions,
  drop `type: ignore`, enforce coverage floor.
- **Phase 4 — Connection Management** (2 plans): auth-aware `pool_recycle=2700`, lifecycle cleanup.
- **Phase 5 — Security Hardening** (2 plans): metadata-based column validation, sqlglot edge tests.
- **Phase 6 — Serialization & Configuration** (2 plans): unified type-handler registry; TOML config.
- **Phase 7 — Wire Orphaned Exports** (2 plans): gap closure — connect the two unwired exports.

## Key Decisions

- `_classify_db_error()` as a **module-level function** (reusable outside ConnectionManager).
- **Type-handler registry**: ordered chain, subclass-first `isinstance` dispatch.
- **Env vars resolved at connection time**, not load time (credential security).
- **Tool-arg precedence**: explicit > config > defaults.
- **Metadata-based validation** with fail-open regex fallback when metadata is unavailable.
- `pool_recycle=2700` — under the 1-hour Azure AD token lifetime.

## Constitution Check

PASS — audit-scoped (Simplicity); registry/`_classify_db_error` satisfy DRY; TDD throughout;
gap-closure phase embodies fail-fast on orphaned wiring.
