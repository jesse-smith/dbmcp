# Project Learnings

Durable, project-specific operating lessons carried forward from the GSD era
(milestones v1.0–v2.1). These are **process/engineering patterns** that have future
implications but don't belong in the [constitution](../.specify/memory/constitution.md)
(which holds binding principles). The constitution gained one clause from this body of
work — the live-warehouse validation rule in Principle III.

Full narrative is in the frozen archive:
[`docs/archive/gsd-planning/RETROSPECTIVE.md`](../docs/archive/gsd-planning/RETROSPECTIVE.md)
(richest) and the per-milestone `MILESTONE-AUDIT.md` files.

---

## L-01 — Live integration is the fastest truth-finder for dialect work

Across v2.0 and v2.1, the **majority of defects surfaced only against a real Databricks
warehouse**, never in mock-based unit tests: Unity Catalog three-part naming, env-var
substitution in URL vs named-config mode, SQL syntax divergence, `connect_timeout`/retry
behavior, driver override, and stale-catalog bleed on pooled connections. v2.0 accumulated
12 quick-tasks and v2.1 another 14, almost all warehouse-only failures.

**Implication:** the recommended **"live smoke-test gate"** — run a real-warehouse smoke
test immediately after any phase that introduces a new dialect or changes identifier
handling, *before* building dependent phases on top of it — was identified in the v2.0
retrospective and reconfirmed (still un-instituted) in v2.1. It is overdue; institute it
for the next dialect/identifier feature. (Now also encoded as a hard rule in Principle III.)

## L-02 — Distinguish "gate it" from "support it" when scoping a deferral

Phase 15 *gated* the Databricks `catalog` (rejected bad input) but did not *thread* it to
cross-catalog metadata — which looked like cross-catalog support but only deferred it. The
gap (CR-02 silent mis-targeting) was invisible until code review, forcing the Phase 15.1
insertion.

**Implication:** when scoping a deferral, state **explicitly** whether the requirement is
*satisfied* or *postponed*. Ask up front: "does gating actually satisfy this requirement, or
just defer it?" A redundant sentence in the spec prevents a whole inserted phase.

## L-03 — Require config fields instead of defaulting when the default is wrong for most cases

Defaulting the TOML `dialect` to `mssql` would have been silently wrong for every Databricks
user; requiring it (D-02) turned a latent prod misconfiguration into an immediate, explicit
failure. The same logic drove the v2.1 breaking change to require a catalog at Databricks
connect time. Relatedly: **dispatch dialect-specific SQL through the strategy, never branch
on `if dialect is None`** — a `_dialect is None` SQLite proxy in QueryService persisted for
weeks as latent breakage for every non-MSSQL path until live Databricks made it visible.

**Implication:** explicit failure beats implicit coercion whenever a default is correct for
fewer than N-1 of N cases. Push per-dialect divergence onto the `DialectStrategy`.

## L-04 — Stateless N-part qualification beats session state on pooled connections

Cross-catalog access via raw 3-part SQL names (no `USE CATALOG`) sidesteps the entire class
of stale-context bugs that session-mutating statements cause on pooled connections. Verified
by an alternating-call UAT showing no catalog bleed. Guarded by a unit test asserting no
`USE CATALOG` is ever emitted.

**Implication:** for any cross-namespace access on pooled connections, prefer fully-qualified
identifiers over per-connection session mutation.

## L-05 — Decimal-phase insertion closes gaps without scope-creep

Both v2.0 (Phase 13.1, audit-driven) and v2.1 (Phase 15.1, code-review-driven) used an
inserted **decimal phase** to close a discovered gap without opening a new milestone or
dragging the current one. This is the project's reliable gap-closure pattern; a milestone
audit (or code review) is a legitimate trigger for it.

## L-06 — Run the milestone audit *before* marking the last phase complete

The v2.0 audit ran as a separate pass after Phase 13 and reported real wiring gaps
(WIRING-01/02/03). It would have been better as a **completion gate** on the final phase.
The audit→milestone pipeline (structured concern gathering → well-scoped milestone) is sound;
just move the audit earlier.

## L-07 — Tracking artifacts drift from reality; reconcile or automate

ROADMAP/REQUIREMENTS checkboxes consistently stayed `[ ]` after the work was actually done
(v1.0 → v2.0; improved but still manual in v2.1). SUMMARY frontmatter was inconsistently
populated, and the GSD `milestone.complete` SDK once auto-extracted code-review rule tags
(`[Rule 3 - Blocking]`) as "accomplishments," requiring a hand-rewrite of MILESTONES.md.

**Implication for spec-kit:** treat status markers ([`STATUS.md`](./STATUS.md), the
per-feature COMPLETE headers) as something to **reconcile deliberately at completion**, and
**always human-review any auto-generated summary** before trusting it.

---

## Verified-good patterns (low-risk, keep doing)

- **TDD red-green-refactor** held across three architecture/correctness milestones with zero
  regressions — the single highest-leverage habit.
- **Atomic format migrations** (v1.0 TOON swap): migrate everything in one coordinated phase
  rather than tool-by-tool, to avoid a mixed-state window.
- **Strategy-over-inheritance for dialects**: adding a dialect = one file in
  `src/db/dialects/` + a registry entry + an optional extra. Zero coupling between dialects.
- **Capability flags** (`supports_indexes`, `supports_catalog`) instead of `isinstance`
  checks in consumer code.
- **Rule-of-Three discipline**: the catalog gate and `CatalogAwareReflector` were each
  extracted only once a third consumer appeared — no premature abstraction.
