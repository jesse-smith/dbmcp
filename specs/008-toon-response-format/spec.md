# Feature Specification: TOON Response Format Migration

> **STATUS: COMPLETE** | Merged: 2026-03-05 | Branch: (GSD milestone v1.0 — archived)

**Origin**: GSD milestone **v1.0** (Phases 1–2). This is a condensed migration summary
reconstructed on the return to spec-kit (2026-06-01). Full per-phase detail —
CONTEXT/RESEARCH/PLAN/SUMMARY/UAT/VERIFICATION — lives in the frozen archive at
[`docs/archive/gsd-planning/milestones/v1.0-phases/`](../../docs/archive/gsd-planning/milestones/v1.0-ROADMAP.md).

## Summary

Migrate every MCP tool response from JSON to **TOON** (Token-Oriented Object Notation),
reducing token consumption for LLM consumers without losing any information, and add a
staleness guard that keeps tool docstrings in sync with the response schemas they document.

## User Scenarios & Testing

### User Story 1 — Token-efficient tool responses (P1)

An LLM agent calls any dbmcp tool and receives a TOON-encoded response that conveys the
same structured information as the prior JSON, but with fewer tokens.

**Acceptance:** all 9 MCP tools return TOON; no tool returns raw `json.dumps` output;
datetime / `StrEnum` / `Decimal` values round-trip correctly through recursive
pre-serialization.

### User Story 2 — Docstring/schema drift protection (P1)

A maintainer changes a tool's response shape; a test fails if the tool's docstring no longer
matches the actual response schema.

**Acceptance:** a parametrized staleness guard covers all 9 tools and fails on documented
drift. (It caught 6 real docstring-schema mismatches during development.)

## Requirements (all validated — v1.0)

- FR-001 — All 9 MCP tools return TOON-encoded responses instead of JSON strings.
- FR-002 — Response docstrings updated to document the TOON structural outline format.
- FR-003 — Staleness test validates docstrings match actual response schemas.
- FR-004 — `toon-python` (`toon_format`) added as a project dependency.
- FR-005 — Existing test suite passes with TOON responses.

## Success Criteria

- SC-001 — Zero `json.dumps` calls remain in tool response paths (40 replaced).
- SC-002 — Staleness guard runs in CI and is green.
- SC-003 — No information lost relative to the prior JSON responses.

## Out of Scope

- Client format negotiation (JSON vs TOON) — LLM-only consumers, hard switch by design.
- Token-savings benchmarking — deferred, not pursued.
