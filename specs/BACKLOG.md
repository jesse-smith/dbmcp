# Feature Backlog

Future, **additive** feature scope deferred during the GSD era (milestones v1.0–v2.1) and
carried into spec-kit so it isn't lost. These are candidate inputs for the next feature
(008+ would be the next number — see [`STATUS.md`](./STATUS.md)). Unlike
[`TECH-DEBT.md`](./TECH-DEBT.md), which tracks fixes to shipped code, this file tracks
**new capability** not yet designed.

Full provenance is in the frozen archive at
[`docs/archive/gsd-planning/`](../docs/archive/gsd-planning/) (see `ROADMAP.md` Backlog and `notes/`).

---

## BL-01 — Cross-dialect catalog/database enumeration tool (DISC-01)

**Captured:** 2026-05-08 (v2.1 scoping tangent) · **Priority:** future

Add a `list_catalogs` / `list_databases` MCP tool that enumerates server-visible databases
or catalogs:
- **MSSQL:** `sys.databases` (informational — listed entries may not be queryable from the
  current connection due to login scope; surface that caveat).
- **Databricks:** `SHOW CATALOGS`.

**Why deferred:** pure additive feature, independent of the v2.1 resolver refactor. Can
reuse the `SHOW CATALOGS` helper introduced in Phase 14 (IDENT-01). Source note:
[`notes/2026-05-08-think-cross-dialect-catalog-enumeration.md`](../docs/archive/gsd-planning/notes/2026-05-08-think-cross-dialect-catalog-enumeration.md).

---

## BL-02 — Cross-catalog FK targets (different catalog than source)

**Captured:** 2026-05-29 (Phase 15.1 planning, RESEARCH Open Q1) · **Priority:** future

Phase 15.1 scoped FK target enumeration to the **resolved catalog only** (KISS). Allowing
`find_fk_candidates` to search for FK targets in a *different* catalog than the source is
deferred. The v2.1 Key Decisions table logs this as the one "— Pending" decision
("FK target enumeration scoped to resolved catalog only").

---

## BL-03 — Cross-dialect `ca_bundle` promotion (Option 3)

**Captured:** 2026-05-28 · **Priority:** low, trigger-based

Quick-task `260528-gsk` shipped a **Databricks-only** `ca_bundle` config field +
`DBMCP_CA_BUNDLE` env fallback (Option 2) for corp-MITM TLS gateways. MSSQL and generic
dialects have no equivalent hook yet.

**Trigger to action** — any of:
- A second dialect (MSSQL, generic, future) hits a corp-MITM `SSLCertVerificationError`.
- A user asks for a unified TLS-trust-bundle config across dialects.
- The dialect protocol is being refactored for another reason (ride that change).

**Scope when triggered:** promote `ca_bundle: str = ""` to a base `ConnectionConfig`
protocol/dataclass field (or mixin) all dialect configs inherit; each dialect's
`create_engine` consumes it via the dialect-appropriate connect-arg
(`_tls_trusted_ca_file` for Databricks; pyodbc has its own; SQLAlchemy generic varies by
driver — research each). Keep `DBMCP_CA_BUNDLE` fallback; one README section for all
dialects. *Out of scope:* per-dialect TLS knobs beyond `ca_bundle` (cipher suites, cert
pinning). Source:
[`todo`](../docs/archive/gsd-planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md).

> The **URL-mode probe `ca_bundle` inheritance** bug (existing Databricks code) is *not*
> here — it's an active fix in [`TECH-DEBT.md`](./TECH-DEBT.md) (TD-02).

---

## BL-04 — Composite-key detection in `find_pk_candidates` (UE-02)

**Captured:** 2026-06-02 (utility eval, finding UE-02) · **Priority:** future

`find_pk_candidates` detects single-column and constraint-backed keys only; on a table whose key is
*composite* it returns an empty candidate list, which reads as "no key exists." In the eval, A2
(`samples.tpch.partsupp`, key `(ps_partkey, ps_suppkey)`) hit exactly this — the dedicated PK tool
returned the worst-case silence on the one table where the answer was composite. This is a
**documented non-goal** of the current tool (its description says so), so it's additive feature
scope, not a bug.

**Scope when triggered:** add a bounded multi-column uniqueness probe (e.g. test 2-column
combinations among the structural single-column candidates), or — cheaper — emit a result note
distinguishing "no key found" from "no *single-column* key found; composite not assessed." See
[`specs/utility-eval/findings.md`](./utility-eval/findings.md) → UE-02.

---

## BL-05 — Surface text truncation at the point of length judgment (UE-05)

**Captured:** 2026-06-02 (utility eval, finding UE-05) · **Priority:** low

`get_sample_data` truncates text values >1000 chars (documented contract) and tracks
`truncated_columns`, but the truncation isn't prominent or per-value. In the eval, A10
(`HL7RawMessage.RawMessage`, max 4000, 32.4% of rows >1000 chars) showed a naive user could
conclude "max ≈ 1000" from sampled rows and size a downstream parser to clip ~⅓ of every long
payload. True lengths are recoverable from `get_column_info` string_stats and the
`... (N chars total)` suffix, so this is UX hardening, not a correctness bug.

**Scope when triggered:** make `truncated_columns` more prominent, annotate per-value, and/or add a
one-line `get_sample_data` docstring hint pointing length questions to `get_column_info`
string_stats. See [`specs/utility-eval/findings.md`](./utility-eval/findings.md) → UE-05.

---

## Provenance notes (deferred sub-scope, no standalone item)

From the GSD `ROADMAP.md` Backlog: the former "Phase 999.1 API consistency pass" was mostly
**consumed into v2.1** — `catalog` kwarg coverage and the `"dbo"` default became IDENT-05/06/07.
Two minor sub-items were **deferred and remain unscheduled** (fold into a future API-consistency
or hardening pass if revisited):
- Row-limit parameter **naming** inconsistency across tools.
- `sample_size` **typing** inconsistency.

These are low-value polish, not tracked as discrete backlog items.
