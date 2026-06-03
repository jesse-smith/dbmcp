# Implementation Plan: Hardening & Cleanup Pass

> **STATUS: COMPLETE** | Merged: 2026-06-03 | Branch: `012-hardening-cleanup`

**Branch**: `012-hardening-cleanup` | **Date**: 2026-06-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-hardening-cleanup/spec.md`

## Summary

A maintenance phase with three known workstreams (TD-01/02/03 from `specs/TECH-DEBT.md`)
and two discovery-driven sweeps (full review + simplification of `src/` and `tests/`). The
known fixes are small and surgical; the sweeps commit to *activities + triage discipline*
recorded in a single `findings.md` ledger, not to pre-enumerated findings.

**Technical approach**: Land the known fixes first (TDD red-green-refactor, one logical
commit each), in priority order TD-02 → TD-01 → TD-03, because TD-02 is the only
operator-facing fix and TD-03's WR-05 is the only behavioral (latency) change needing live
validation. Then run the `src/` sweep, then the `tests/` sweep, dispositioning every finding
in the ledger per the clarified triage bar. Re-verify every file:line against current `main`
before editing — **already confirmed that IN-02/03/04 is mostly done** (a shared
`_check_table_exists`/`_is_cross_catalog` already exists in `analysis_tools.py`), so FR-006
collapses to a consistency check + the IN-01 `_sql.py` row-shape assertion.

## Technical Context

**Language/Version**: Python 3.11+ (running on 3.13.1 in `.venv`, managed by `uv`)

**Primary Dependencies**: mcp[cli] ≥1.0.0, SQLAlchemy ≥2.0.0, pyodbc ≥5.0.0, sqlglot,
azure-identity ≥1.14.0, databricks-sqlalchemy — all existing, **no new dependencies**.

**Storage**: N/A (in-memory connection management + on-demand query results only).

**Testing**: pytest; `uv run pytest tests/`. 1119 passing / 146 skipped on `main` today.

**Target Platform**: Linux/macOS server hosting a FastMCP stdio server.

**Project Type**: Single project — MCP server (`src/`, `tests/`).

**Performance Goals**: WR-05 — restore the Databricks DESCRIBE EXTENDED fast path on the
cross-catalog branch so `get_column_info` reads precomputed stats in one metadata call
instead of N live Tier-2 aggregate queries (COUNT/MIN/MAX/distinct per column). No regression
on the default-catalog path. No other perf targets — this is hardening, not optimization.

**Constraints**:
- 85% coverage floor (`SC-003`), never dropped — including mid-sweep consolidation.
- Complexity gate max 15 via `scripts/check_complexity.py` (NOT bare `complexipy`); CI lints
  `src/` only, not `tests/`.
- No shipped MCP tool contract (names, params, response keys/shape) changes unless a surfaced
  bug forces it, in which case the delta is called out before landing (`FR-014`/`SC-005`).
- Live validation against the Databricks warehouse + StemSoftClinicTest wherever reachable;
  only the corp-MITM-specific TD-02 probe path may defer to follow-up UAT (`FR-017`/`SC-006`).
- `dbmcp-test` server must be reconnected after merging `src/` changes mid-session so live
  probes reflect post-change behavior (not stale session code).

**Scale/Scope**: ~30 `src/` modules to review; 5 known fix sites; the `tests/` tree
(1119 tests). Sweeps are scoped to the trees as they stand on this branch; BACKLOG items
BL-01/02/03 stay out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First (YAGNI) | ✅ PASS | The phase *removes* debt and dead code. WR-05 deletes a dead branch by making it live; no speculative abstraction. FR-006 shrinks because the abstraction already exists — no second helper. |
| II. DRY (rule of three) | ✅ PASS | FR-006 is a DRY fix (the 3-tool scaffold) — already satisfied. The shared `findings.md` ledger and `_analysis_error_response` are existing single-sources-of-truth. |
| III. Test-First Development | ✅ PASS — **central** | Every code fix is red-green-refactor. The live-warehouse clause is directly invoked: WR-05 and the cross-catalog reflector change MUST be validated against the live Databricks warehouse (SC-008), not just mocks. TD-01 is pure test addition. |
| IV. Robustness / explicit errors | ✅ PASS — **central** | WR-01 (narrow bare `except Exception`→`SQLAlchemyError`) and WR-02 (misleading row guards) and IN-01 (fail-fast on row shape) are all direct applications of "MUST NOT swallow errors silently" / "fail fast on programmer errors." |
| V. Performance by Design | ✅ PASS | WR-05 restores a deliberate cache-style fast path with explicit gating; measured live (SC-008), not assumed. |
| VI. Code Quality / clarity | ✅ PASS | The whole `src/` sweep serves this principle. Complexity gate (≤15 project / constitution says ≤10 — see deviation below) and ≤50-line functions enforced on touched code. |
| VII. Minimal Dependencies | ✅ PASS | Zero new dependencies. |

**Quality Gates**: Tests pass, no new skips without reason; coverage ≥85%; zero lint
warnings on `src/`; complexity ≤15.

**Deviation — complexity budget**: The constitution names cyclomatic complexity ≤10
(§Quality Gates), but this project's *enforced* gate is cognitive complexity ≤15 via
`scripts/check_complexity.py` (raised deliberately during GSD v2.0/Phase 13, recorded in
`specs/STATUS.md`/LEARNINGS). This plan follows the **enforced project gate (≤15)**, which is
stricter to bypass than the constitution's advisory number and is what CI actually checks.
No function may *cross* the gate as a result of a fix (Edge Cases); if a fix would, the
function is refactored to stay under, never bypassed. Logged here rather than in Complexity
Tracking because it is a pre-existing, project-wide, CI-encoded standard, not a new violation
introduced by this feature.

**Refactoring discipline**: Refactor commits stay separate from behavior-change commits
(§Development Workflow). WR-05 is the one behavior change and lands as its own commit with its
live-validation evidence; the IN/WR-01/WR-02 robustness fixes and sweep simplifications are
separate atomic commits.

*Post-Phase-1 re-check*: ✅ No new violations introduced by the design below.

## Project Structure

### Documentation (this feature)

```text
specs/012-hardening-cleanup/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (WR-05 type conversion, IN-02/03/04 status, sweep method)
├── data-model.md        # Phase 1 — Finding / Disposition entities + findings.md ledger schema
├── quickstart.md        # Phase 1 — how to run the fixes, sweeps, gates, and live validation
├── findings.md          # Created during implementation (FR-010) — the sweep ledger
├── checklists/
│   └── requirements.md   # Spec quality checklist (already complete)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

> No `contracts/` directory. This feature exposes **no new external interface** — its
> contract guarantee is the *inverse*: the nine shipped MCP tool contracts stay byte-for-byte
> stable (`FR-014`). The "contract under test" is captured as a stability assertion in
> quickstart.md, not as new contract files.

### Source Code (repository root)

```text
src/
├── analysis/
│   ├── column_stats.py      # WR-01, WR-02, WR-05 (fast path + get_column_data_type TypeEngine)
│   ├── _sql.py              # IN-01 (list_tables row-shape assertion), CatalogAwareReflector
│   ├── pk_discovery.py      # sweep review
│   └── fk_candidates.py     # sweep review
├── db/
│   ├── connection.py        # TD-01 (tests only), TD-02 (URL-mode probe ca_bundle)
│   ├── dialects/            # sweep review (databricks.py ca_bundle/type machinery)
│   ├── identifiers.py       # sweep review
│   └── metadata.py          # sweep review
├── mcp_server/
│   └── analysis_tools.py    # FR-006 consistency check (helper already exists)
└── …(remaining modules)     # full src/ sweep coverage (SC-002)

tests/
├── unit/
│   └── test_connect_with_config_databricks.py   # TD-01 (reuse _make_engine_spy)
└── …                        # full tests/ sweep (US3): consolidation, intent-refactor
```

**Structure Decision**: Single-project MCP server, unchanged. All edits are in-place to
existing modules; the only new files are `findings.md` (the ledger) and TD-01 test additions
to an existing test file. No new packages, modules, or directories.

## Complexity Tracking

> No unjustified constitution violations. The one deviation (cognitive-complexity ≤15 vs the
> constitution's cyclomatic ≤10) is a pre-existing CI-encoded project standard, explained in
> the Constitution Check above — not a new violation requiring justification here.
