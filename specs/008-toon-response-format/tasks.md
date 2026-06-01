# Tasks: TOON Response Format Migration

> **STATUS: COMPLETE** | Merged: 2026-03-05 | Branch: (GSD milestone v1.0 — archived)

**Origin**: GSD milestone **v1.0**, 2 phases / 5 plans / 8 tasks, all complete.
This is a condensed checklist reconstructed from the archived GSD ROADMAP/SUMMARY files.
Per-plan detail: [`docs/archive/gsd-planning/milestones/v1.0-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v1.0-ROADMAP.md).

## Phase 1 — Atomic TOON Migration (3 plans)

- [X] Build `encode_response()` wrapper with recursive pre-serialization (datetime, StrEnum, Decimal).
- [X] Atomically swap all 9 MCP tools from JSON to TOON (40 `json.dumps` → `encode_response`).
- [X] Rewrite all 9 tool docstrings in TOON structural outline format.
- [X] Add `parse_tool_response()` test helper; migrate 64+ `json.loads` test call sites.

## Phase 2 — Staleness Guard (2 plans)

- [X] Implement docstring parser (`ast`-based) and bidirectional field comparison utilities.
- [X] Add parametrized staleness guard test across all 9 tools (21 tests, 99% coverage).
- [X] Verify guard catches real drift (caught 6 docstring-schema mismatches during development).

**Outcome:** 5 plans in ~19 minutes total; zero regressions; `toon_format` added as dependency.
