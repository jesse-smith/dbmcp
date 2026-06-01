# GSD Planning Archive (frozen)

> **This directory is frozen, read-only history.** It is the complete `.planning/`
> working set from the period (2026-03 → 2026-05) when this project was driven by the
> **GSD** orchestrator. The project has since returned to **spec-kit**; live project
> state now lives under [`specs/`](../../../specs/). Nothing in this directory is
> consulted by any active workflow — it is preserved for provenance and reference only.

## Why this exists

GSD ships no export-to-spec-kit tooling, so when the project migrated back to spec-kit
the GSD context was relocated here intact (via `git mv`, full history preserved) rather
than reconstructed file-for-file. The **forward-looking content** that mattered — open
work, deferred items, backlog, and durable learnings — was carried into spec-kit-native
registries. This archive is the system of record for everything else.

## Where the forward-looking content went

| GSD source (here) | Migrated to (live) |
|---|---|
| `todos/pending/` (open work, tech debt) | [`specs/TECH-DEBT.md`](../../../specs/TECH-DEBT.md) |
| `ROADMAP.md` Backlog, deferred scope, `notes/` | [`specs/BACKLOG.md`](../../../specs/BACKLOG.md) |
| `RETROSPECTIVE.md` operating patterns | [`specs/LEARNINGS.md`](../../../specs/LEARNINGS.md) |
| Durable engineering principles | [`.specify/memory/constitution.md`](../../../.specify/memory/constitution.md) |
| Milestone history (v1.0–v2.1) | [`specs/STATUS.md`](../../../specs/STATUS.md) rows 008–011 + per-milestone feature dirs |

The four GSD milestones map to spec-kit feature dirs:
`008-toon-response-format` (v1.0), `009-concern-handling` (v1.1),
`010-multi-dialect-support` (v2.0), `011-databricks-identifier-fixes` (v2.1).
Those dirs are condensed summaries; this archive holds the full per-phase detail.

## Reading map (start here)

- **`MILESTONES.md`** — at-a-glance summary of all four shipped milestones (v1.0–v2.1).
- **`RETROSPECTIVE.md`** — cross-milestone lessons and patterns (the richest learnings doc).
- **`PROJECT.md`** — project charter, full requirements matrix, and the 34-entry Key Decisions table.
- **`STATE.md`** — final GSD state snapshot: deferred items, quick-task commit SHAs, accumulated context.
- **`ROADMAP.md`** — milestone/phase breakdown and the original backlog.
- **`milestones/`** — per-milestone ROADMAP / REQUIREMENTS / MILESTONE-AUDIT archives.
- **`phases/`** — per-phase artifacts (CONTEXT, RESEARCH, PLAN, SUMMARY, REVIEW, SECURITY, UAT, VERIFICATION) for the most recent milestone; older phases are under `milestones/vX.Y-phases/`.
- **`quick/`** — 26 ad-hoc quick-task records (dated `YYMMDD-xxx-slug/`).
- **`todos/done/`** — 18 resolved todos with commit references.

_Frozen 2026-06-01 on migration from GSD back to spec-kit._
