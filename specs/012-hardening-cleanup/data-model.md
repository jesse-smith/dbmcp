# Phase 1 Data Model: Hardening & Cleanup Pass

This feature has **no runtime data model** (no new entities, tables, or response shapes — see
FR-014/SC-005). The only structured artifact is the **`findings.md` review ledger**, whose
schema is defined here so SC-002 ("every module reviewed, every finding dispositioned") is
mechanically verifiable.

---

## Entity: Finding

A discovery-driven observation from a sweep. The unit of work for User Stories 2 and 3.

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | `SRC-NN` for `src/` findings, `TST-NN` for `tests/` findings. Sequential, unique, never reused. |
| `location` | string | `file:line` (or `file` for whole-module observations), re-verified against current `main`. |
| `severity` | enum | `critical` \| `warning` \| `info` — matching the 15.1-REVIEW.md scale. |
| `description` | string | What is wrong / what could be simpler, in one or two sentences. |
| `disposition` | Disposition | Mandatory — no finding may lack one (SC-002). See below. |

**Validation rules**:
- Every finding MUST have a `disposition` before phase end (SC-002 → no undispositioned rows).
- A `critical` or correctness-class finding MUST be dispositioned `fixed` (the triage bar
  fixes all correctness bugs regardless of location) — it may NOT be `logged`.
- `id` prefixes partition the ledger into the two sweep sections (FR-010 `src/`, FR-012
  `tests/`).

---

## Entity: Disposition

The triage outcome for a finding (clarify Q1 triage bar, FR-011).

| Variant | When | Required reference |
|---------|------|--------------------|
| `fixed` | Correctness bug (any location), OR a simplification local to TD-01/02/03 code being touched | Commit SHA + test name proving the fix |
| `verified` | Reviewed and found already-correct / already-refactored (e.g. IN-02/03/04) — no change needed | Note explaining why no action |
| `logged` | Larger/standalone refactor, or out-of-scope cleanup | The `TECH-DEBT.md` / `BACKLOG.md` ID it was moved to |

**State transitions**: a finding is born `open` (no disposition) and moves exactly once to a
terminal disposition (`fixed` / `verified` / `logged`). No reopening within the phase — a
re-surfaced issue is a new `id`.

> `verified` is an addition beyond the spec's two-way `fixed`/`logged` split, made necessary by
> D-04: IN-02/03/04 is already done, so "we looked and it's correct" needs a first-class,
> auditable outcome distinct from "we changed it" and "we deferred it". Recorded in the ledger
> legend; does not change FR-011's intent (every finding still has an explicit disposition).

---

## Entity: Known tech-debt item

The enumerated TD-01/02/03 work. Not part of the ledger (it predates the sweeps) but tracked
to closure.

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | `TD-01` \| `TD-02` \| `TD-03` (+ sub-IDs WR-01/02/05, IN-01..04). |
| `source` | path | The frozen GSD todo + `15.1-REVIEW.md` provenance. |
| `resolution` | enum | `fixed` (landed + tested) \| `clarified` (e.g. FR-003 `_tls_trusted_ca_file` over-spec, D-02). |
| `closure` | action | Struck/moved in `TECH-DEBT.md` per that file's convention (FR-009/SC-001). |

---

## The `findings.md` ledger — file layout

Created at implementation start (FR-010), maintained through both sweeps. Frontmatter mirrors
15.1-REVIEW.md so the existing tooling/reader expectations carry over.

```markdown
---
phase: 012-hardening-cleanup
reviewed: 2026-06-0X
src_modules_total: <N>
src_modules_reviewed: <N>     # must equal total at close (SC-002)
findings: { critical: x, warning: y, info: z, total: t }
dispositions: { fixed: a, verified: b, logged: c }   # a+b+c == total
---

## src/ module coverage checklist        # SC-002 evidence
- [x] src/analysis/column_stats.py
- [x] src/analysis/_sql.py
- [ ] …                                   # unchecked = unreviewed (visible gap)

## src/ findings (SRC-NN)
### SRC-01 — <title>
**Location:** file:line · **Severity:** warning
**Description:** …
**Disposition:** fixed (commit abc1234, test `test_…`)

## tests/ findings (TST-NN)
### TST-01 — <title>
…
```

**Invariants checked at phase close** (these are the SC-002/SC-007 gates):
- `src_modules_reviewed == src_modules_total` (every module checked off).
- `dispositions.fixed + verified + logged == findings.total` (no open finding).
- Every `fixed` row cites a commit + test; every `logged` row cites a TECH-DEBT/BACKLOG ID.
- `tests/` section records before/after test counts where consolidation happened (SC-007).
