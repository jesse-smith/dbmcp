# Implementation Plan: TOON Response Format Migration

> **STATUS: COMPLETE** | Merged: 2026-03-05 | Branch: (GSD milestone v1.0 — archived)

**Origin**: GSD milestone **v1.0** (Phases 1–2, 5 plans, shipped 2026-03-05).
Condensed summary; full detail in
[`docs/archive/gsd-planning/milestones/v1.0-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v1.0-ROADMAP.md)
and `RETROSPECTIVE.md`.

## Summary

Two-phase migration: (1) atomically swap all 9 tools from JSON to TOON via a single
`encode_response()` wrapper with recursive pre-serialization; (2) add a staleness guard that
parses tool docstrings (via the `ast` module, avoiding circular imports) and compares fields
bidirectionally against the real response schema.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: mcp[cli], `toon_format` (new), existing SQLAlchemy/pyodbc stack
**Storage**: N/A (in-memory serialization)
**Testing**: pytest + pytest-asyncio
**Project Type**: MCP server

## Approach & Key Decisions

- **Atomic swap, no JSON fallback** — only LLM consumers exist; simplicity over backward
  compat (research flagged mixed JSON/TOON state as a pitfall).
- **`encode_response()` wrapper** as the single serialization entry point for all tools.
- **`parse_tool_response()` test helper** replacing 64+ `json.loads` calls in tests.
- **`ast` module for docstring extraction** — avoids circular imports with MCP server modules.
- **TypeError on unrecognized types (strict)** — explicit failure over silent `str()` fallback.
- **Staleness guard as ongoing regression protection** for docstring↔schema sync.

## Phases

- **Phase 1 — Atomic TOON Migration** (3 plans): wrapper + swap all 9 tools + docstring rewrite.
- **Phase 2 — Staleness Guard** (2 plans): docstring parser, bidirectional field comparison,
  parametrized test (21 tests, 99% coverage).

## Constitution Check

PASS — atomic swap satisfies Simplicity; wrapper satisfies DRY; TDD throughout
(red-green-refactor, zero regressions).
