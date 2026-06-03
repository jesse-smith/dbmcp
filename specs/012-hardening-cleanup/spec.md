# Feature Specification: Hardening & Cleanup Pass

> **STATUS: COMPLETE** | Merged: 2026-06-03 | Branch: `012-hardening-cleanup`

**Feature Branch**: `012-hardening-cleanup`

**Created**: 2026-06-01

**Status**: Draft

**Input**: User description: "012 Hardening & Cleanup Pass — resolve the three open tech-debt items (TD-01, TD-02, TD-03) plus two discovery-driven review-and-simplify sweeps across src/ and tests/, triaging any surfaced issues."

## Overview

This is a maintenance feature, not a new capability. It has three known workstreams (the
open tech-debt items in `specs/TECH-DEBT.md`) and two discovery-driven workstreams (full
review + simplification sweeps of `src/` and `tests/`) whose concrete findings do not exist
until the sweeps run. The spec therefore commits to the **known fixes** as testable
requirements and to the **review activities + triage discipline** as the deliverable shape
for the discovery work — it does not pretend to enumerate findings not yet found.

The two stakeholders:

- **MCP-client operators** — benefit directly from TD-02 (actionable catalog list on
  corp-MITM networks) and from any correctness bug the `src/` sweep surfaces and fixes.
- **Project maintainers** — benefit from the regression coverage (TD-01), the robustness and
  dedup fixes (TD-03), and a leaner, intent-revealing test suite (the `tests/` sweep).

## Clarifications

### Session 2026-06-01

- Q: What is the triage bar for the discovery sweeps — which findings get fixed now vs. logged? → A: Fix all correctness bugs; fix simplifications only where they are local to code already being touched for the known TD-01/02/03 fixes; log larger/standalone refactors to TECH-DEBT.md/BACKLOG.md with provenance.
- Q: How should TD-03 WR-05 (dead Databricks DESCRIBE EXTENDED fast path on the cross-catalog branch) be resolved — gate it off, or make it fire? → A: Make the fast path fire cross-catalog (Option B), pulling the perf optimization into scope. Rationale: cross-catalog queries are common in Databricks and recomputing column stats via Tier-2 aggregates is costly, so the unreachable fast path is a real latency cost, not a nice-to-have. Requires the cross-catalog reflector (`get_column_data_type`) to return a `TypeEngine` so the `isinstance` gate fires; needs live perf validation against the Databricks warehouse.
- Q: Where are discovery-sweep findings recorded, and how is "100% dispositioned" (SC-002) verified? → A: A single `specs/012-hardening-cleanup/findings.md` ledger (following the Phase-15.1 `15.1-REVIEW.md` precedent). Every finding gets an ID, location, severity, and disposition — `fixed` (with commit/test reference) or `logged` (with the TECH-DEBT.md/BACKLOG.md ID it was moved to). SC-002 is verified by confirming the ledger covers all `src/` modules and that no finding lacks a disposition.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Close the three open tech-debt items (Priority: P1)

The known, enumerable debt carried from the GSD era is resolved and struck from
`TECH-DEBT.md`. This is the highest-confidence, lowest-risk slice: every item already has a
precise file:line location and a prescribed fix from prior audits/reviews.

**Why this priority**: These are concrete, agreed fixes with known scope. TD-02 has direct
operator-facing value (corp-MITM users currently lose the actionable catalog list). TD-03's
WR-01 was explicitly flagged "promote to urgent if it ever masks a real incident." Landing
these first delivers value even if the discovery sweeps find nothing.

**Independent Test**: Can be fully tested by running the new/changed unit tests for TD-01,
TD-02, and the seven TD-03 findings, confirming the full suite stays green at the 85%
coverage floor, and confirming `TECH-DEBT.md` no longer lists TD-01/02/03 as open.

**Acceptance Scenarios**:

1. **Given** the Databricks `connect_with_config` path, **When** a config supplies
   `catalog`/`schema_name` as `${ENV_VAR}` references, **Then** a test asserts the values
   resolve from the environment in the captured engine kwargs (TD-01 gap 1).
2. **Given** the Databricks connect path, **When** `dialect.create_engine` raises a
   `SQLAlchemyError`, **Then** a test asserts it is wrapped in `ConnectionError` with the
   host string present in the message (TD-01 gap 2).
3. **Given** a URL-mode connection that triggers the "Databricks catalog is required" error,
   **When** the IDENT-01 enrichment helper builds its probe engine to run `SHOW CATALOGS`,
   **Then** the probe engine inherits `ca_bundle` (and `_tls_trusted_ca_file`) from the
   inbound URL, and a unit test asserts the probe receives `ca_bundle` when the URL carries
   one (TD-02).
4. **Given** `_try_describe_extended_stats`, **When** the underlying call fails, **Then** the
   handler catches only `SQLAlchemyError` (not bare `Exception`) so auth/network/injection
   failures are no longer silently swallowed (TD-03 WR-01).
5. **Given** the aggregate-row accessors in `column_stats.py`, **When** a row has an
   unexpected shape, **Then** the misleading `row[1] if row else 0` guards are replaced so
   behavior is correct and intent-revealing (TD-03 WR-02).
6. **Given** the three analysis tools (`get_column_info`, `find_pk_candidates`,
   `find_fk_candidates`), **When** they resolve a table and check existence, **Then** the
   copy-pasted cross-catalog scaffolding is replaced by one shared helper that also unifies
   the lazy `MetadataService` import and the "table not found" message template
   (TD-03 IN-02/03/04 collapse into one fix).
7. **Given** the Databricks DESCRIBE EXTENDED fast path, **When** a column is resolved
   cross-catalog, **Then** the fast path **fires** (it no longer silently falls through to
   Tier-2): the cross-catalog reflector returns a `TypeEngine` so the `isinstance` gate
   passes, precomputed stats are used cross-catalog, and the docstrings match the now-true
   behavior (TD-03 WR-05, resolved as Option B).
8. **Given** `list_tables` SHOW TABLES row handling in `_sql.py`, **When** a row arrives,
   **Then** the documented `(database, tableName, isTemporary)` shape is asserted/fail-fast
   rather than silently returning a database name as a table name (TD-03 IN-01).

---

### User Story 2 - Full code review + simplification sweep of src/ (Priority: P2)

Every source file in `src/` is reviewed for correctness bugs and for
reuse/simplification/efficiency cleanups — not just the five files the Phase-15.1 review
covered. Surfaced issues are triaged: fix-now (correctness or low-risk cleanup within this
phase's scope) or log-later (to `TECH-DEBT.md` / `BACKLOG.md` with provenance).

**Why this priority**: The prior review's narrow file coverage is a known blind spot. A
correctness bug found here could be operator-facing; simplifications reduce future
maintenance cost. Discovery-driven, so it ranks below the known fixes.

**Independent Test**: Can be tested by confirming a review record exists covering all `src/`
modules, every finding has a disposition (fixed / logged with ID), fixes land with tests,
and the suite stays green within the coverage and complexity gates.

**Acceptance Scenarios**:

1. **Given** the full `src/` tree, **When** the review sweep completes, **Then** every module
   has been reviewed and the findings are recorded with a severity and a disposition.
2. **Given** a surfaced correctness bug, **When** it is fixed in this phase, **Then** a
   regression test accompanies the fix and the tool's external contract is unchanged unless
   the bug itself requires a contract change (which is called out explicitly).
3. **Given** a surfaced cleanup that is out of scope or higher-risk, **When** it is triaged
   to defer, **Then** it is logged to `TECH-DEBT.md` or `BACKLOG.md` with enough provenance
   to action later.

---

### User Story 3 - Full test review + simplification sweep of tests/ (Priority: P3)

The `tests/` suite (1119 passing / 146 skipped today) is reviewed for redundancy, shallow
coverage, and intent-vs-implementation drift. Redundant or shallow tests are consolidated;
tests that encode implementation detail rather than intent are refactored; hard-to-write
tests are treated as design signals and noted. Coverage must not drop below the 85% floor.

**Why this priority**: Test-suite quality is leverage on all future work, but it is the
lowest operator-facing risk and depends on the `src/` state stabilizing first (P1/P2 changes
may add or remove tests), so it runs last.

**Independent Test**: Can be tested by confirming coverage stays ≥85% after consolidation,
the suite still passes, the passing/skipped counts and rationale for changes are recorded,
and any "hard-to-write test → design signal" observations are captured.

**Acceptance Scenarios**:

1. **Given** the test suite, **When** redundant tests covering identical behavior are found,
   **Then** they are consolidated without reducing coverage below the floor.
2. **Given** a test asserting on implementation detail rather than observable behavior,
   **When** it is identified, **Then** it is refactored to encode intent, or its
   implementation coupling is documented as deliberate.
3. **Given** a behavior that is hard to test, **When** the difficulty signals a design
   problem in the code under test, **Then** the observation is captured (fixed if in scope,
   else logged).

---

### Edge Cases

- **A sweep finds a correctness bug whose fix would change a shipped tool contract.** The
  change is not made silently; it is surfaced with the rationale and the contract delta
  called out before landing (per the no-silent-contract-change constraint).
- **A fix would push a function over the complexity gate (max 15).** The function is
  refactored to stay under the gate, or the fix is restructured — the gate is not bypassed.
- **A test consolidation would drop coverage below 85%.** The consolidation is reworked to
  preserve coverage, or backed out.
- **Live validation is unreachable for a given fix** (e.g., TD-02 needs a corp-MITM TLS
  network). The fix lands with unit-test coverage and the live check is explicitly deferred
  to follow-up UAT rather than blocking the phase.
- **The `src/` sweep surfaces more debt than is reasonable to fix in one phase.** Excess is
  triaged to `TECH-DEBT.md`/`BACKLOG.md` rather than expanding scope without bound.

## Requirements *(mandatory)*

### Functional Requirements

**Known tech-debt fixes (TD-01 / TD-02 / TD-03):**

- **FR-001**: The suite MUST gain a test asserting env-var substitution of
  `catalog`/`schema_name` in the Databricks `connect_with_config` path (TD-01 gap 1).
- **FR-002**: The suite MUST gain a test asserting `SQLAlchemyError` from the Databricks
  `create_engine` is wrapped in `ConnectionError` with the host in the message (TD-01 gap 2).
- **FR-003**: The IDENT-01 catalog-enrichment probe engine MUST inherit `ca_bundle` from the
  inbound URL so the actionable catalog list survives corp-MITM TLS, with a unit test
  asserting the probe receives `ca_bundle` (TD-02). *(Scope clarification, D-02: this FR
  originally also named `_tls_trusted_ca_file`, but that value is derived inside
  `create_engine` from `ca_bundle`, so forwarding `ca_bundle` alone is sufficient — no
  separate `_tls_trusted_ca_file` threading is needed. Recorded in findings.md.)*
- **FR-004**: `_try_describe_extended_stats` MUST narrow its exception handling from bare
  `Exception` to `SQLAlchemyError` (and ideally distinguish "DESCRIBE EXTENDED unsupported"
  from infra errors that should propagate) (TD-03 WR-01).
- **FR-005**: The misleading aggregate-row guards in `column_stats.py` (`row[1] if row else
  0` and siblings) MUST be corrected to guard width or trust the aggregate contract
  (TD-03 WR-02).
- **FR-006**: The duplicated cross-catalog existence-check scaffolding across the three
  analysis tools MUST be replaced by one shared helper that also subsumes the duplicated
  lazy `MetadataService` import and unifies the "table not found" message template
  (TD-03 IN-02/03/04).
- **FR-007**: The Databricks DESCRIBE EXTENDED fast path MUST fire on the cross-catalog
  branch (TD-03 WR-05, Option B). The cross-catalog reflector (`get_column_data_type`) MUST
  return a `TypeEngine` so the `isinstance` gate passes and `get_column_info` uses precomputed
  stats cross-catalog instead of recomputing them via Tier-2 aggregate queries; docstrings
  MUST be updated to match. This is a behavioral (latency) change to the cross-catalog
  `get_column_info` path — its result contract (response keys/shape) MUST remain unchanged
  (see FR-014).
- **FR-008**: `list_tables` SHOW TABLES row handling MUST assert/fail-fast on its documented
  row shape rather than silently returning a database name as a table name (TD-03 IN-01).
- **FR-009**: On completion, `TECH-DEBT.md` MUST no longer list TD-01, TD-02, and TD-03 as
  open; resolved items are struck/moved per the file's own convention.

**Discovery-driven sweeps (src/ and tests/):**

- **FR-010**: Every module under `src/` MUST be reviewed for correctness bugs and
  reuse/simplification/efficiency cleanups, with findings recorded in a single
  `specs/012-hardening-cleanup/findings.md` ledger — each finding carrying an ID, location,
  severity, and disposition (following the Phase-15.1 `15.1-REVIEW.md` precedent).
- **FR-011**: Every surfaced finding in `findings.md` MUST receive an explicit disposition
  using this triage bar: (a) **correctness bugs** are fixed in this phase regardless of
  location (with an accompanying regression test); (b) **simplifications/cleanups** are fixed
  only where they are local to code already being touched for the known TD-01/02/03 fixes;
  (c) **larger or standalone refactors** are logged to `TECH-DEBT.md`/`BACKLOG.md` with
  provenance rather than expanding this phase's change surface. A `fixed` disposition MUST
  reference its commit/test; a `logged` disposition MUST reference the TECH-DEBT/BACKLOG ID.
- **FR-012**: The `tests/` suite MUST be reviewed for redundancy, shallow coverage, and
  intent-vs-implementation drift, with consolidations and refactors recorded in the same
  `findings.md` ledger (a distinct section/prefix from the `src/` findings).
- **FR-013**: Hard-to-write tests surfaced during the `tests/` sweep MUST be treated as
  design signals — the observation captured, and the underlying design issue fixed (if in
  scope) or logged.

**Cross-cutting constraints (apply to all workstreams):**

- **FR-014**: No change MAY alter a shipped MCP tool's external contract unless a surfaced
  bug requires it, in which case the contract delta MUST be called out explicitly before
  landing.
- **FR-015**: Test coverage MUST remain at or above the 85% floor throughout.
- **FR-016**: Every function touched MUST remain within the complexity gate (max 15, measured
  via `scripts/check_complexity.py`, not the bare tool).
- **FR-017**: Fixes MUST be validated live against the Databricks warehouse and
  StemSoftClinicTest wherever reachable; only the corp-MITM-specific TD-02 probe check MAY be
  deferred to follow-up UAT.
- **FR-018**: Changes SHOULD be committed at task/logical-unit granularity (one commit per
  logical task), following red-green-refactor TDD where a code change is involved.

### Key Entities

- **Tech-debt item**: A known, enumerated fix (TD-01/02/03) with a source location, prescribed
  fix, priority, and effort estimate; tracked in `specs/TECH-DEBT.md`.
- **Review finding**: A discovery-driven observation from a sweep, with a location, severity,
  and a disposition (fixed / logged). The unit of work for User Stories 2 and 3.
- **Disposition**: The triage outcome for a finding — `fixed` (landed this phase with a test)
  or `logged` (moved to `TECH-DEBT.md`/`BACKLOG.md` with provenance).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: TD-01, TD-02, and TD-03 are all resolved — no longer listed as open in
  `TECH-DEBT.md` — with their prescribed fixes landed and tested.
- **SC-002**: 100% of `src/` modules have been reviewed in the sweep (not just the 5 files
  the prior review covered), and 100% of findings in `findings.md` have an explicit
  disposition (`fixed` with commit/test ref, or `logged` with a TECH-DEBT/BACKLOG ID) — the
  ledger has no undispositioned entries.
- **SC-003**: The full test suite passes and code coverage is at or above 85% at phase end.
- **SC-004**: Every function touched during the phase is within the complexity gate (max 15);
  the gate is never bypassed.
- **SC-005**: No shipped MCP tool's external contract changed without an explicit,
  documented rationale.
- **SC-006**: Every reachable fix was validated live (Databricks warehouse / StemSoftClinicTest);
  the only deferred live check is the corp-MITM-specific TD-02 probe path, recorded as
  follow-up UAT.
- **SC-008**: The WR-05 fast path is confirmed firing cross-catalog against the live
  Databricks warehouse — `get_column_info` on a cross-catalog table returns the same result
  contract via the precomputed-stats path that it previously returned via Tier-2, confirming
  the optimization is active and result-preserving.
- **SC-007**: The test suite is measurably leaner or clearer where redundancy/drift was found
  — consolidations and intent-refactors are recorded with before/after counts — and no
  net coverage loss results.

## Assumptions

- The prescribed fixes in `TECH-DEBT.md` for TD-01/02/03 remain accurate against current
  `main`; file:line references will be re-verified at implementation time before editing
  (code may have shifted since the audit).
- Live validation environments (Databricks warehouse, StemSoftClinicTest via the
  `dbmcp-test` server) are reachable in at least one working session; the `dbmcp-test` server
  is reconnected after merging `src/` changes so probes reflect post-change behavior.
- The two sweeps are scoped to the existing `src/` and `tests/` trees as they stand on the
  `012-hardening-cleanup` branch; new feature work (BACKLOG items BL-01/02/03) is explicitly
  out of scope and stays deferred.
- "No behavioral change to shipped tool contracts" refers to the externally observable MCP
  tool interfaces (tool names, parameters, response shape/keys); internal refactors that
  preserve those are permitted and expected.
- CI lints `src/` only (not `tests/`); the complexity gate runs via `scripts/check_complexity.py`.
