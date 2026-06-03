# Adversarial Utility Evaluation — dbmcp

**Date:** 2026-06-02
**Question:** When a competent analyst/engineer points dbmcp at real data to do real work,
does it help them reach a correct answer — or does it mislead them? Standard of comparison:
raw SQL via the `databricks` MCP.

This is a **utility** eval, distinct from the prior **robustness** pass (TD-11/TD-12/L-08,
resolved). We hunt the failure class robustness testing misses:
*technically-correct-but-practically-harmful* — a clean, confident, well-formed answer that
quietly leads to a wrong conclusion.

> **Phase A was discovery-only**; findings were logged here and routed to `specs/TECH-DEBT.md` /
> `specs/BACKLOG.md`. **Update (2026-06-02):** by user decision the three misleading-high findings
> (UE-01/03/04) were then *fixed* before Phase B — see **Fix Outcomes** below. No PHI row dumps —
> counts/structure only.

---

## Method — four roles, strict bias isolation

| Role | Who | Knows | Blind to |
|------|-----|-------|----------|
| Orchestrator | main loop | everything | — |
| Executor | fresh isolated sub-agent, one per task per toolset | a realistic persona + the task + **one** MCP toolset | that this is an eval; the oracle; the sharp-edge list |
| Oracle | orchestrator, computed independently via raw SQL **before** executors run | ground truth | — |
| Judge | separate sub-agent, one per transcript / A-B pair | task + transcript + oracle + sharp edges | which toolset produced a transcript (A/B unlabeled) |

**Bias controls:** executors never told it's an eval / never shown oracle or sharp edges;
each uses exactly one toolset (stray use flagged); fresh agent per task (no learning effect);
A/B transcripts judged unlabeled.

**Oracle independence:**
- **Databricks** truth via the `databricks` MCP — **fully independent** of dbmcp.
- **MSSQL** truth via dbmcp-test `execute_query` raw SELECTs — **asterisk**: same server, but a
  thin SELECT-passthrough on a *different code path* from the analysis tools under judgment, not
  a fully independent MCP. MSSQL correctness findings are marked with this caveat.

**Preflight (2026-06-02):** all three toolsets live. dbmcp-test→StemSoftClinicTest (mssql, 246
`dbo` tables) and dbmcp-test→bmtct (databricks, 22 schemas) both connected; `databricks` MCP
reaches the warehouse (`samples.tpch.customer` = 750,000). **Spawned sub-agents can invoke both
`mcp__dbmcp-test__*` and `mcp__databricks__*`** — scripted fallback NOT needed.

---

## Oracle ground truth — Phase A (recorded before any executor ran)

⚖ = A/B head-to-head task (run by both a dbmcp-test executor and a databricks-raw executor).

### Databricks (independent oracle)

- **A1 ⚖ — `samples.tpch.customer.c_acctbal` (avg/spread/outliers).** n=750,000;
  mean **4501.03**, stddev **3175.36**, min **−999.99**, max **9999.99**, p25 1755.49,
  median **4490.57**, p75 7251.57. Negative balances are real low-end outliers.
  *Sharp edge:* Databricks fast-path `get_column_info` returns **null mean/stddev by design**.
- **A2 ⚖ — `samples.tpch.partsupp` unique identifier.** rows=4,000,000;
  distinct ps_partkey=1,000,000; distinct ps_suppkey=50,000;
  **distinct (ps_partkey, ps_suppkey)=4,000,000 → the composite (partkey,suppkey) is the key.**
  Neither column is unique alone. *Sharp edge:* `find_pk_candidates` has **no composite-key
  detection**.
- **A3 ⚖ — `samples.nyctaxi.trips` avg fare from a sample.** n=**21,932** (small table);
  true mean fare **12.35**, min −8.0, max 275.0, median 9.0. *Sharp edge:* `get_sample_data`
  default `top` is **not representative**.
- **A4 — tpch FK map.** Canonical TPC-H: customer.c_nationkey→nation.n_nationkey;
  nation.n_regionkey→region.r_regionkey; supplier.s_nationkey→nation.n_nationkey;
  partsupp.ps_partkey→part.p_partkey; partsupp.ps_suppkey→supplier.s_suppkey;
  orders.o_custkey→customer.c_custkey; lineitem.l_orderkey→orders.o_orderkey;
  lineitem.(l_partkey,l_suppkey)→partsupp; l_partkey→part; l_suppkey→supplier.
  *Sharp edge:* FK tool is a heuristic — may surface false positives / miss real ones.
- **A5 — profile `samples.tpch.customer` via the bmtct connection (cross-catalog).** n=750,000;
  zero nulls in c_custkey/c_name/c_acctbal/c_nationkey/c_mktsegment; distinct c_custkey=750,000
  (clean PK). *Expected to be a clean pass — sanity floor.*
- **A6 — `bmtct.cerner_dm.demographics` data-quality profile.** rows=190,782;
  `deceased_dt` **95.6% null** (8,395 non-null — benign: most patients alive);
  `mrn` 182,270 distinct (**8,512 duplicate MRNs** — real DQ issue);
  `birth_dt` ~4.05% null; `sex_disp` ~12.9% null; `deceased_cd` 0% null;
  `age_years` **min −7875, max 224** (impossible — real DQ issue), mean 42.37.
  *Sharp edge:* null mean misleading; null-% coherence.

### MSSQL (oracle via execute_query raw SELECT — asterisk applies)

- **A7 — `dbo.PerformedActs` 20 most-recent + total count.** **total = 1,391,510.**
  *Sharp edge:* `execute_query` with a top-level ORDER BY drops `rows_available` (TD-08/SRC-05),
  so a paged/limited recency query can hide the true total.
- **A8 — `dbo.PerformedActs_QuantitativeObservation.Result_Value` (avg/spread).**
  n=62,857; non-null=58,706; mean **920,415.36**, stddev **74,285,089**, min 0, max 6.0e9.
  (Enormous spread = mixed units across test types — itself a DQ caution.)
  *Cross-dialect drift:* MSSQL Tier-2 path **populates** mean/stddev; Databricks fast-path
  (A1) does **not** → capability drift across dialects is itself a utility finding.
- **A9 — `dbo.PerformedActs` unique identifier.** 1,391,510 rows = 1,391,510 distinct
  `PerformedActID` (identity, declared PK). Clean constraint-backed answer — contrast to A2.
- **A10 — `dbo.HL7RawMessage.RawMessage` long-text sample + summarize.** 130,942 rows;
  max_len **4000**, avg 723; **42,412 rows (32.4%) exceed 1000 chars.**
  *Sharp edge:* dbmcp truncates text >1000 chars — a summary built on sampled rows silently
  omits ~⅓ of each long payload.
- **A11 — undeclared FK for `dbo.PerformedActs.ClonedFromID`.** 752,193 non-null;
  **747,612 (99.4%) resolve to a real `PerformedActID`** → genuine undeclared self-referential
  FK to `dbo.PerformedActs.PerformedActID`. *Sharp edge:* FK heuristic on a real schema.

---

## Findings ledger — Phase A

Severity key: **misleading-high** (clean confident output that leads a careful-enough-to-trust
user to a wrong conclusion) / **friction-med** (correct outcome but the tool fought the user or
returned an unhelpful signal) / **cosmetic-low**.

### UE-01 — `find_fk_candidates` runs overlap INTERSECT against type-incompatible targets → hard error · **misleading-high** · CONFIRMED CROSS-DIALECT
- **Tasks/tools:** A4 (Databricks, `find_fk_candidates`) + A11 (MSSQL, `find_fk_candidates`).
- **What the tool returned:** A4 — probing `lineitem.l_orderkey → orders` threw
  `INCOMPATIBLE_COLUMN_TYPE` because the tool ran its INTERSECT against the DATE column
  `o_orderdate`. A11 — probing `ClonedFromID` threw `Error converting nvarchar to bigint`
  because it ran INTERSECT against the NVARCHAR column `SystemProfiles.ID`.
- **What was true:** both relationships are real (l_orderkey→o_orderkey 100% overlap;
  ClonedFromID→PerformedActID 99.4%). The correct type-compatible target exists in each case.
- **Why it misleads/harms:** the tool errors out instead of skipping the incompatible target.
  A caller who trusts the tool would record **"no FK relationship found"** for a column that
  has one. Both blind agents only recovered by abandoning the tool and writing manual SQL — i.e.
  they succeeded *despite* the one tool whose entire job is this question. **This is the same
  defect class on both dialects**, so it's structural (candidate selection doesn't pre-filter to
  the source column's type before emitting set operations), not a dialect quirk.
- **Disposition:** **FIXED** (commit `2a44144`, this branch). `find_candidates` now skips a
  target when source/target type categories differ and neither is `"other"`, via the shared
  `type_category()` extracted to `src/analysis/_sql.py` (broadened to classify Databricks/generic
  type spellings, not just MSSQL). The incompatible target is filtered *before* the INTERSECT, so
  no hard DB error; an additive `type_incompatible_skipped` count is surfaced when > 0. See
  Fix Outcomes below.

### UE-02 — `find_pk_candidates` cannot detect composite keys; returns empty (reads as "no key") · **friction-med** · working-as-intended-but-under-surfaced
- **Task/tool:** A2 (Databricks, `find_pk_candidates` on `samples.tpch.partsupp`).
- **What the tool returned:** empty candidate list (no single-column or constraint-backed key).
- **What was true:** the key is the composite `(ps_partkey, ps_suppkey)` (4M distinct = 4M rows).
- **Why it misleads/harms:** on the one table where the answer *is* composite, the dedicated PK
  tool returns the worst-case silence. "No candidates" reads as "no key exists → table needs a
  surrogate / can't be safely deduped," the opposite of the truth. The agent dodged it by
  empirical verification, but the empty result is a latent misread.
- **Disposition:** `logged → BACKLOG` (composite-key detection is a known non-goal — documented in
  the tool's own description — but the empty-vs-misleading framing warrants either a doc note or a
  multi-column probe). No code change this pass.

### UE-03 — `get_column_info` distinct counts are approximate (HLL) but unlabeled at point of output · **misleading-high**
- **Tasks/tool:** A5 + A6 (Databricks, `get_column_info`).
- **What the tool returned:** A5 — `distinct c_custkey = 725,800` for a column that is *perfectly
  unique*. A6 — `person_id` approx 190,132 vs exact 190,771.
- **What was true:** A5 c_custkey distinct = exactly 750,000 (= row count, clean PK). A6 exact
  distinct differs from the approximation by hundreds.
- **Why it misleads/harms:** on a uniqueness/PK assessment the HLL undercount **manufactures
  phantom duplicates on the cleanest possible data** — a careful-but-trusting analyst would
  conclude "≈24k duplicate keys, not PK-safe, needs dedup," which is exactly backwards. The
  approximate nature is documented in the tool description but is **not marked inline in the
  result**, so it reads as exact. Both agents caught it only by running an exact `COUNT(DISTINCT)`.
- **Disposition:** **FIXED** (commit `9c5ec1e`, this branch). `ColumnStatistics` gains an
  always-present `distinct_count_approximate` boolean — `True` on the Databricks DESCRIBE EXTENDED
  fast path (HLL), `False` on the exact Tier-2 `COUNT(DISTINCT)` path. The flag is emitted
  unconditionally so an absent value is never read as "exact." **Follow-up still open:**
  `find_pk_candidates` could be misled by an approximate count when assessing uniqueness — logged
  as a separate TECH-DEBT item (force-exact or consult the new flag); NOT implemented this pass.
  See Fix Outcomes below.

### UE-04 — `get_sample_data` `modulo` method silently returns 0 rows on Delta/Databricks · **misleading-high**
- **Task/tool:** A6 (Databricks, `get_sample_data` method=`modulo`).
- **What the tool returned:** 0 rows, no error.
- **What was true:** the table has 190,782 rows; `top` sampling worked fine.
- **Why it misleads/harms:** a silent empty result is **indistinguishable from a genuinely empty
  table** — the most dangerous failure mode. A consumer could conclude "no data" and skip the
  table. The agent recognized the method was unsupported and fell back to `top`, but nothing in
  the response said the method failed.
- **Disposition:** **FIXED** (commit `990bdd7`, this branch). Root cause was **not** an
  unsupported method — it was **float division**: Databricks/generic `/` produces a DOUBLE, so the
  predicate `_rn % (_total / n) = 0` was essentially never true for integer `_rn`. Databricks now
  uses Spark integer division `DIV`; generic uses ANSI-portable `CAST(_total / n AS INTEGER)`;
  MSSQL (already integer `/`) is unchanged. Defense-in-depth: a modulo sample that still returns 0
  rows falls back to TOP (mirrors the existing TABLESAMPLE→TOP path), so a silent-empty never
  reaches the caller. Live-proven (`DIV` → 5 rows on `bmtct.cerner_dm.demographics`).
  See Fix Outcomes below.

### UE-05 — `get_sample_data` truncates text >1000 chars; truncation not surfaced at the point of length judgment · **friction-med** · doc/UX gap
- **Task/tool:** A10 (MSSQL, `get_sample_data` on `HL7RawMessage.RawMessage`).
- **What the tool returned:** sample row text clipped at 1000 chars (per the tool's own contract).
- **What was true:** `RawMessage` max length = 4000; **42,412 rows (32.4%) exceed 1000 chars**.
- **Why it misleads/harms:** a user characterizing "typical length / can we parse this" by
  eyeballing sampled rows would conclude **max ≈ 1000** and size a downstream parser to clip ~⅓
  of every long payload. The agent avoided it by reading true lengths from `get_column_info`
  string_stats; a naive user using only `get_sample_data` would have been misled. The response
  does carry a `truncated_columns` field, but it isn't prominent and isn't per-value.
- **Disposition:** `logged → BACKLOG` (documented truncation behavior; UX hardening — make
  `truncated_columns` prominent / annotate per-value / hint "use column stats for length").

### UE-06 — Databricks `get_column_info` returns null mean/stddev (cross-dialect capability drift) · **cosmetic-low** · working-as-intended, already documented
- **Tasks/tool:** A1 (Databricks null mean/stddev) vs A8 (MSSQL Tier-2 populates them).
- **Status:** **No-issue / confirmed by-design.** This is the TD-11 resolution (columnar metadata
  has no Σx/Σx², so mean/stddev cannot be derived from Delta footers; the fast path correctly
  leaves them null). Logged here only to record that the cross-dialect drift is *real and
  observable to users*: an analyst gets mean/stddev for free on MSSQL but must compute it in SQL
  on Databricks. The A1 agent hit the null, recognized the limitation, and worked around it.
- **Disposition:** `no-issue` (documented contract). Drift noted for the cross-dialect-consistency
  discussion, not as a defect.

### Meta-finding — the analysis tools' job is to standardize + accelerate agent exploration; when they force a confirmatory SQL query, they are net-slower than the query alone
**Audience framing (corrected):** the tools are built for **LLM agents**, not SQL-illiterate
humans. Their purpose is to *speed up exploration and standardize the queries used for it* — not
to compensate for an inability to write SQL. The consuming agent is, by construction, SQL-fluent.
That reframes the efficiency bar precisely: a tool earns its place only if calling it is **faster
than writing the equivalent SQL once**. A tool that returns null / empty / wrong / errors and
thereby forces the agent to *also* write the confirmatory query is **strictly slower than skipping
it** — two round-trips (tool + SQL) where one (SQL) would do, plus the interpretation cost of
reconciling them.

Across A1, A3, A7, A8 the documented *query-path* sharp edges (Databricks null mean,
`top`-not-representative, ORDER-BY-drops-`rows_available`, Tier-2 drift) **never bit**, because the
blind executors routed quantitative work to `execute_query` (raw SELECT). `execute_query` is the
dialect-agnostic workhorse and was reliable throughout. Every friction/misleading finding
(UE-01..05) lives in the four *analysis* tools (`find_fk_candidates`, `find_pk_candidates`,
`get_column_info`, `get_sample_data`).

The call-sequence analysis below (added post-review) shows the tools are **not cruft** — A9 and A10
were solved by analysis tools *alone*, A4 did 8/10 FK edges via the tool, A6 used them as a
scouting layer that surfaced the −7875 impossible age. But in the cases where they failed, they
failed by forcing the exact tool+SQL double-spend the tool exists to prevent. The defect priority
follows directly: **UE-01/03/04 don't just risk a wrong answer — they convert the tool from an
accelerator into a tax.** That is the central utility takeaway of Phase A.

## Scorecard — Phase A

All 11 dbmcp-test executors reached the **correct** answer (incl. the sanity-floor A9, clean PASS).
"Misled-risk" = would a careful-but-trusting user have been misled had they stopped at the tool's
output? Round-trips = dbmcp-test tool calls.

| # | Correct | Misled-risk (if tool trusted) | Round-trips | Notes / sharp edge |
|---|---------|-------------------------------|-------------|--------------------|
| A1 ⚖ | yes | no (null-stat caught) | 4 | UE-06 friction; recovered via SQL |
| A2 ⚖ | yes | **yes** (empty PK = "no key") | 4 | UE-02 |
| A3 ⚖ | yes (±0.6%) | no | 2 | get_sample_data sidestepped |
| A4 | yes | **yes** (FK tool error = "no FK") | 19 | **UE-01** |
| A5 | yes | **yes** (phantom dups) | 4 | UE-03 |
| A6 | yes (exceeded) | **yes** (UE-03 + UE-04) | 13 | UE-03, **UE-04** |
| A7 | yes | no (separate COUNT) | 3 | ORDER-BY quirk sidestepped |
| A8 | yes (exemplary) | no | 5 | robust stats beyond ask |
| A9 | yes | no | 3 | sanity floor PASS |
| A10 | yes | **yes** (naive user: max≈1000) | 4 | UE-05 |
| A11 | yes | **yes** (FK tool error = "no FK") | 8 | **UE-01** (cross-dialect) |

**A/B head-to-head (⚖):** raw SQL vs dbmcp-test, judged unlabeled (label map revealed here).
- **A1** (X=dbmcp, Y=raw): judge → **raw wins narrowly** — both correct; dbmcp spent a round-trip
  on `get_column_info` that returned null stats; raw was leaner.
- **A2** (X=raw, Y=dbmcp): judge → **raw slight edge** — both correct; dbmcp's `find_pk_candidates`
  returned a misleading empty result the agent had to route around.
- **A3** (X=dbmcp, Y=raw): judge → **dbmcp narrow edge** — dbmcp's LIMIT-sample headline (12.43)
  was closer to truth (12.35) than raw's TABLESAMPLE range (12.40–12.70, which excluded truth).
- **Net:** correctness is a wash (all four arms correct). The differentiator is that dbmcp's
  *analysis* tools added round-trips / misleading signals; its `execute_query` path matched raw.
  **dbmcp does not beat the raw standard; it ties on correctness and loses slightly on friction —
  driven entirely by the analysis tools, not the query path.**

## Call-sequence analysis — did agents try the analysis tools, or skip to SQL? (added post-review)

Motivating question: is the "route to `execute_query`" pattern evidence the analysis tools are
**cruft** (agents skip them entirely), or evidence they were **tried and fell short** (agents used
them, then had to confirm/replace with SQL)? Classified from the tool logs of all 11 dbmcp-test
transcripts. Audience = LLM agents; the bar is *"is calling the tool faster than writing the SQL
once?"*

| # | Reached for an analysis tool? | Outcome | Tool+SQL double-spend? |
|---|---|---|---|
| A1 | tried `get_column_info` | returned **null** mean/stddev → filled with SQL | **yes** (tool wasted) |
| A2 | tried `find_pk_candidates` | returned **empty** → composite found via SQL | **yes** (tool wasted) |
| A3 | **skipped** `get_sample_data` | SQL sampling directly | no (clean skip; sampling pref) |
| A4 | used `find_fk_candidates` ×7 | **tool did 8/10 edges**; SQL only on the 1 type-error | partial (mostly tool-served) |
| A5 | used `get_column_info` | **wrong positive** (725,800 distinct on a unique key) → overridden by SQL | **yes** (tool actively misled) |
| A6 | used `get_column_info`+`get_sample_data`+`find_pk_candidates` | scouting layer **surfaced −7875 age**; exact counts via SQL | partial (tool earned its place) |
| A7 | **skipped** (none applicable) | "count + most-recent" has no matching analysis tool | no (no applicable tool) |
| A8 | **skipped** `get_column_info` | the one clean skip-that-would-have-worked | n/a — but needed median/IQR/trim the tool can't produce anyway |
| A9 | used `find_pk_candidates` | **sufficient, no SQL needed** | **no — tool fully served** |
| A10 | used `get_column_info` string_stats | **the hero — no SQL at all**; string_stats dodged the truncation trap | **no — tool fully served** |
| A11 | used `get_column_info`; tried `find_fk_candidates` | get_column_info gave ranges; FK tool **errored** → SQL | partial (one tool served, one wasted) |

**Verdict on the cruft hypothesis: rejected.** 8 of 11 agents reached for an analysis tool first;
only A8 is a clean skip-when-it-would-have-helped (and even there the agent needed robust stats the
tool can't compute). A9 and A10 were solved by analysis tools *alone*; A4/A6 were materially
tool-served. The tools are load-bearing in a real subset.

**But the failure mode is the efficiency-killer, not a safety net.** Where the tools fell short
(A1 null, A2 empty, A5 wrong, A11/A4 error) they forced a **tool+SQL double-spend** — the agent
paid for the tool call *and* the confirmatory/replacement query. For an SQL-fluent agent that is
strictly slower than writing the one query. So the tools split cleanly into:
- **Earning their place** (faster than SQL): A9, A10 fully; A4, A6 substantially. The standardized
  structured output (string_stats, constraint-backed PK, multi-table FK overlap) genuinely beat
  hand-SQL here.
- **Acting as a tax** (slower than SQL): A1, A2, A5, A11 — the UE-01/03/04 cases. The tool didn't
  accelerate; it added a round-trip the agent then had to undo.

**Severity re-justification (the post-review point):** UE-03 (HLL approximate distinct) is the
**single highest-severity finding**, because A5 is the *only* case where a tool returned a
confident **wrong positive** rather than going quiet. Null/empty/error (A1/A2/A11) are
self-announcing — the agent sees the gap and fills it; cost is one wasted round-trip. A wrong
positive on a *uniqueness check of a perfectly clean key* is the one failure that an agent could
propagate without noticing (this one was caught only because the executor independently verified).
That asymmetry — silent-gap vs confident-wrong — is the right axis for prioritizing the fixes.

## Fix Outcomes — UE sub-plan (2026-06-02, between Phase A and Phase B)

By user decision the three misleading-high findings were fixed before Phase B (deviating from the
discovery-only stance), because **B2 leans directly on `find_fk_candidates` at scale** — testing it
while UE-01 still errored would partly measure a known bug. Each was an independent TDD
red-green-refactor cycle; MSSQL stayed the green reference throughout.

| Finding | Commit | Observable contract change | Tests |
|---------|--------|----------------------------|-------|
| **UE-04** | `990bdd7` | modulo returns rows on Databricks/generic; `sampling_method` may report `top` if the defensive fallback fires | dialect SQL-shape locks ×3, query.py fallback, sqlite modulo integration |
| **UE-01** | `2a44144` | type-incompatible FK candidates no longer appear (and no longer hard-error under `include_overlap`); new optional `type_incompatible_skipped` | cross-dialect categorizer table, skip/keep/wildcard, overlap-not-called, model serialization, staleness |
| **UE-03** | `9c5ec1e` | every `get_column_info` column gains an always-present `distinct_count_approximate` boolean | model default/emit, fast-path True, Tier-2 False, staleness |

**Verified root cause corrections during the fix:** UE-04 was first hypothesized (by an Explore
agent) to be "undefined ordering on Delta"; live diagnosis proved it was float-vs-integer division
(`190782 / 5 = 38156.4` DOUBLE), which changed the fix from "add ORDER BY" to "use `DIV`/`CAST`."

**Gates at each commit:** full suite green (1160 → 1219 → 1221 passed, 168 skipped), `ruff check
src/` clean, complexity ≤15 (`scripts/check_complexity.py`), coverage 92.06% (floor 85%).

**Deferred (logged, not implemented this pass):**
- **UE-02** (composite-key detection in `find_pk_candidates`) → BACKLOG (documented non-goal).
- **UE-05** (truncation prominence) → BACKLOG (a docstring hint at most; no code change).
- **UE-03 follow-up** (`find_pk_candidates` force-exact / consult `distinct_count_approximate`) →
  TECH-DEBT as a separate finding.

**Live re-validation (2026-06-02, after `/mcp` reload of the dev-mirror — all PASS):**
- **UE-04 PASS** — `get_sample_data(modulo, sample_size=5)` on `bmtct.cerner_dm.demographics`
  returned **5 rows** (Phase A: 0), `sampling_method: modulo` (the `DIV` fix carried it; the
  defensive TOP fallback did not need to fire).
- **UE-01 PASS** — `find_fk_candidates(ClonedFromID, include_overlap=True)` on MSSQL `PerformedActs`
  returned **267 candidates with no DB error** (Phase A: `Error converting nvarchar to bigint`) and
  **`type_incompatible_skipped: 1`** — the NVARCHAR target that previously crashed the whole call is
  now skipped and surfaced.
- **UE-03 PASS** — `get_column_info`: Databricks `cerner_dm.demographics.person_id` →
  `distinct_count: 190132` (< 190,782 rows) with **`distinct_count_approximate: true`** (the A5/A6
  phantom-duplicate signal, now labeled); MSSQL `dbo.PerformedActs.PerformedActID` →
  `distinct_count: 1391510` (= row count, exact) with **`distinct_count_approximate: false`**.

## Executor prompt appendix (blindness audit)

Every Phase-A executor was a fresh isolated sub-agent given a persona + the task + one toolset.
None were told it was an eval, shown the oracle, or shown the sharp-edge list. Personas:
A1 analyst, A2 engineer, A3 analyst, A4 engineer onboarding, A5 analyst, A6 DQ analyst,
A7 analyst, A8 analyst, A9 engineer, A10 analyst, A11 engineer reverse-engineering. The three
⚖ raw-SQL arms (A1/A2/A3) got the identical task text with the only-tool = `databricks` MCP.
Full prompt text is reproducible from the orchestrator transcript; no prompt referenced the
eval, the expected answer, or any documented sharp edge. **Blindness audit: PASS.**

## Phase A executor outcomes (orchestrator log, oracle in hand)

Format: tool path → result vs oracle. dbmcp-test unless marked (raw).

- **A1 dbmcp-test** — `get_column_info` returned **mean/std_dev = null** (Databricks fast path);
  agent *noticed* and fell back to `execute_query` → mean 4501.03, sd 3175.36, flagged 68,166
  negative balances. **Correct.** Friction: had to work around null stats.
- **A1 raw** — `execute_query` AVG/STDDEV/percentiles directly → 4501.03 / 3175.36, symmetric,
  no outliers, 68,166 negatives. **Correct.** No friction.
- **A2 dbmcp-test** — `get_table_schema` (no PK) + `find_pk_candidates` returned **empty
  (no candidate)**; agent fell back to `execute_query` → composite (ps_partkey,ps_suppkey),
  4M=4M. **Correct.** Tool gave no help on the composite.
- **A2 raw** — DESCRIBE + one aggregate → composite key, neither alone unique. **Correct.**
- **A3 dbmcp-test** — did **not** use `get_sample_data`; used `execute_query` with
  `LIMIT 10000` subquery → avg 12.43 (true 12.35). **Correct (±0.6%)**, flagged LIMIT-bias.
  *The `top`-not-representative trap was sidestepped by avoiding get_sample_data.*
- **A3 raw** — two TABLESAMPLE queries → 12.43 & 12.69, answer ~12.50. **Correct**, noted neg fares.
- **A4 dbmcp-test** — mapped all TPC-H FKs at 100% overlap via `find_fk_candidates`, BUT the tool
  **errored on l_orderkey→orders** (`INCOMPATIBLE_COLUMN_TYPE`: ran INTERSECT against the DATE
  column o_orderdate); agent worked around via manual `execute_query`. **Correct**, 19 tool calls.
- **A5 dbmcp-test** — `get_column_info` reported **approximate distinct c_custkey = 725,800**
  (true 750,000); agent caught the approx-vs-exact gap via `execute_query COUNT(DISTINCT)` →
  confirmed clean PK, 0 nulls. **Correct** — but the unlabeled approx count *contradicted
  uniqueness* and a less careful analyst would conclude duplicates exist.
- **A6 dbmcp-test** — deep DQ (13 calls): found duplicate MRNs (8,512), impossible ages
  (min −7875, 1900-01-01 sentinel = 20,786 rows), code-0=not-recorded traps. **Correct, exceeded
  oracle.** Hit two tool rough edges: `get_column_info` approx distinct (person_id 190,132 vs
  exact 190,771) and **`get_sample_data` modulo returned 0 rows silently** on Delta.
- **A7 dbmcp-test** — ran a separate `execute_query COUNT(*)` = 1,391,510 + TOP 20 ORDER BY.
  **Correct.** *ORDER-BY-drops-rows_available trap not exercised* (agent counted separately).
- **A8 dbmcp-test** — did **not** use `get_column_info`; `execute_query` → mean 920,415 / sd 74M,
  correctly called it junk, gave median 14 / IQR / trimmed mean 271, flagged mixed units.
  **Correct + better than the naive ask.** *Tier-2 drift not exercised (get_column_info skipped).*
- **A9 dbmcp-test** — `find_pk_candidates` → PerformedActID constraint-backed PK. **Correct, clean.**
  (Contrast A2: tool shines on declared single-col PKs, silent on composites.)
- **A10 dbmcp-test** — `get_column_info` string_stats gave accurate max_len 4000 / avg 723;
  `get_sample_data` rows (display-truncated at 1000) used only for structure. **Correct**
  characterization. *dbmcp's >1000-char display truncation was latent — rescued by string_stats;
  an agent eyeballing only sample rows would have concluded max ≈ 1000.*
- **A11 dbmcp-test** — `find_fk_candidates` **errored** (`Error converting nvarchar to bigint`:
  INTERSECT against nvarchar SystemProfiles.ID); agent went manual via self-LEFT-JOIN →
  self-FK to PerformedActID, 99.39% match. **Correct.** *Same find_fk_candidates type-mismatch
  defect as A4 — now confirmed cross-dialect (Databricks + MSSQL).*

---

# Phase B — open-ended tasks (against fixed code)

Phase A was trap-probe (designed around known sharp edges). **Phase B is open-ended realistic
work**, and 2 of 3 tasks deliberately re-exercise the now-fixed tools (UE-01 `find_fk_candidates`,
UE-03 `get_column_info` distinct) to answer the post-fix question: *do they now earn their place vs
raw SQL, or merely stop crashing?* Same four-role bias isolation; A/B (⚖) judged unlabeled; no PHI
(counts/structure only).

**Final task set (B4 dropped by user decision — B1+B2+B3 is already a long run):**

| Task | Dialect | Scope guard | Tool under test | Ground truth | ⚖ |
|------|---------|-------------|-----------------|--------------|---|
| B1 | Databricks | 2 schemas only (no catalog search) | discovery loop + 3 fixed tools | `mv_micro_labs` ref | yes |
| B2 | Databricks | v500 only; ~6–8 `*_ID` cols; `*_CD` collapsed; breadth>depth | find_pk + find_fk @ 602M×5,476 | **none** (plausibility + spot-check) | no |
| B3 | MSSQL | views read-only, not as source | schema-exploration suite | user's SSRS queries (asterisk) | yes (asterisk) |

## B1 ⚖ — Micro-labs cross-source unification (scoped to `cerner_src.v500` + `caboodle_src.warehouse_fullaccess`)

**Task (verbatim to executor):** *"I need microbiology lab results extracted into a single coherent
table for downstream use. The source data lives in two schemas: `cerner_src.v500` and
`caboodle_src.warehouse_fullaccess` (Cerner and Epic respectively). The relevant data may be spread
across multiple tables or at multiple grains — I need one row per result, each with: an order id,
test name, panel name, collection date, and patient MRN. Check the results for problematic values
(nulls, sentinels, anything that would break a downstream consumer). Deliver: (1) the SQL query that
produces the unified table, and (2) a short writeup of what you found — where the data lived, how you
reconciled the two sources and the grains, and the data-quality issues. Confine all exploration to
those two schemas. Show the tool calls you used."*

**Scope rationale:** hard-confined to the two raw schemas — keeps the executor off the user's
finished artifact (`bmtct.ml_infections_ref.mv_micro_labs`) AND its curated intermediates
(`bmtct.ml_infections_src.mv_{cerner,epic}_micro_labs`), forcing genuine raw-table work.

**Oracle (independent, `databricks` MCP — recorded 2026-06-03; reference, not exact-match key):**
- **Final reference artifact** `bmtct.ml_infections_ref.mv_micro_labs`: **238,978 rows** (Epic
  137,918 / Cerner 101,060); grain = one row per result (distinct culture_id 160,856 < rows → multi
  result per order); 0 null mrn/collection_date/test_name; 1,369 distinct MRNs. *(MV itself is out of
  scope — used only as the orchestrator's gold reference.)*
- **Cerner raw path** (`cerner_src.v500`): `MIC_IC_ORDERS` → LEFT JOIN `ORDERS` (status) → filtered
  by EXISTS in `MIC_TASK_LOG`; latest report via `MIC_TASK_LOG` window → `MIC_REPORT_RESPONSE`
  (RESPONSE_TEXT); organisms via `MIC_TASK_LOG` → `CODE_VALUE`; test/source/site/status decode via
  `CODE_VALUE` (×5); LOINC via `concept_ident_mic_rpt`. MRN: MV used
  `bmtct.bmtct_datamodels.mv_patient_crosswalk` (**out of scope** — a confined executor must instead
  source MRN from `v500.person_alias`, a legitimate harder path / gotcha).
- **Epic raw path** (`caboodle_src.warehouse_fullaccess`): `LabComponentResultFact` → INNER JOIN
  `LabTestFact` (specimen, `Section IN ('MICROBIOLOGY','MOLECULAR MICROBIOLOGY')`) → `LabComponentDim`
  (panel=`commonname`, test=`Name`) → `PatientDim` (MRN; filters `isvalid=1`, `iscurrent=1`,
  `crf.count=1`, `_hassourcecerner=0`).
- **Scoring:** judge scores coherence/correctness against this reference path + grain + DQ, allowing
  open-ended column-shape variation (e.g. derived `panel`, `culture_id` vs "order id"). The
  cross-schema MRN sourcing (crosswalk out of scope) is the key open-ended bridge to watch.

## B2 — `clinical_event` reverse-engineering (bounded; `cerner_src.v500`)

**Task (verbatim to executor):** *"`clinical_event` (catalog `cerner_src`, schema `v500`) is a large
fact-like table, but we don't have its relationships documented. Produce a relationship map: (1)
identify its primary key; (2) identify the columns that are foreign-key candidates; (3) for the most
important structural relationships — bound this to the ~6–8 highest-value FK columns, e.g. the
entity/`*_ID` references, NOT the dozens of code (`*_CD`) lookup columns, which you can treat
collectively as 'code lookups against the shared code table' without enumerating each — find the
likely target table in `cerner_src.v500` and infer the cardinality (one-to-one / many-to-one /
one-to-many). Confine target search to `cerner_src.v500`. Time-box: prefer breadth over exhaustive
verification — a ranked map with confidence levels beats a perfect answer on two columns. Show the
tool calls you used."*

**Bounds rationale:** clinical_event has 90 columns incl. ~40 `*_CD` lookups that nearly all point at
the universal `code_value` table; unbounded, the agent would chase 50+ candidates × 5,476 tables.
Caps: ~6–8 `*_ID` cols, `*_CD` collapsed, target universe = v500, breadth>depth.

**No gold answer (user has no ground truth).** Scored on plausibility + tool-utility-vs-raw-SQL, with
orchestrator spot-checks below.

**Oracle (partial, `databricks` MCP, recorded 2026-06-03 — PK exact; FK via 1M-row TABLESAMPLE):**
- **Rows 602,381,343; PK `CLINICAL_EVENT_ID`** = 602,381,343 distinct (clean single-col PK).
- **`PERSON_ID` → person.PERSON_ID** 100% resolve (many-to-one).
- **`ENCNTR_ID` → encounter.ENCNTR_ID** 100% resolve (many-to-one).
- **`ORDER_ID` → orders.ORDER_ID** 100% of *non-zero*, but **~87% are `0` sentinel** (most clinical
  events aren't order-linked — key gotcha; "resolves" only after excluding 0).
- **`PERFORMED_PRSNL_ID` → prsnl.PERSON_ID** 99.995% of non-zero (**prsnl PK is `PERSON_ID`, not
  `PRSNL_ID`** — Cerner quirk; a tool/agent assuming `PRSNL_ID` target-col name will miss it).
- **`PARENT_EVENT_ID`** self-referential to `clinical_event.EVENT_ID` (hierarchy; ~78% point to a
  different event, rest self/zero).
- **`EVENT_ID`, `SRC_EVENT_ID`** event-grouping refs (self/within-domain). **~40 `*_CD` → code_value**
  (the collapse class). All 8 expected targets (person, encounter, orders, prsnl, code_value,
  order_action, encntr_alias, ce_blob) confirmed present in v500.

## B3 ⚖ — SSRS observations report (MSSQL; views read-only, not as source)

**Task (verbatim to executor):** *"I'm writing an SSRS report pulling all observations for a given
patient, along with the user who signed off on each observation. Requirements: observations should be
grouped by their parent observation where one exists; prior versions of an observation must be
excluded (current version only); one row per observation, with patient MRN, observation date,
observation name, observation value, and the user who locked the record after observation entry (if
the record was locked). Also give me a summary interpreting what you found in the schema. Database:
`StemSoftClinicTest`. Do not use the pre-built views as your query source — they are extremely slow;
you may read them only to understand the schema/relationships. Show the tool calls you used."*

**Gotchas (surfaced by requirements, NOT leaked as hints):** observations = `PerformedActs`;
PerformedActs is SCD-II (prior-version exclusion needed); parent-observation grouping is itself
another observation; many tables are "base table" candidates; templates are XML; locked-by user is a
separate join. "Don't use naive views as source, may read for structure" is verbatim per user.

**Oracle (MSSQL via dbmcp-test `execute_query` raw — asterisk: same-server, different code path;
recorded 2026-06-03 after `kinit`):** The schema is a **class-table-inheritance (CTI) entity model**,
not a flat observations table. Canonical path:

- **Observation = `PerformedActs`** (base, 1,391,510 rows; PK `PerformedActID` identity). **SCD-II via
  `ClonedFromID`** (self-ref to prior version; A11 confirmed 99.4% resolve). *Current-version filter:*
  a row is the current version iff **no other row's `ClonedFromID` points to it** (i.e.
  `PerformedActID NOT IN (SELECT ClonedFromID WHERE ClonedFromID IS NOT NULL)`) — the prior-version
  exclusion the task requires.
- **1:1 inheritance chain:** `PerformedActs` → `PerformedActs_Observation` (1.39M, 1:1 on
  `PerformedActID`; carries `Name` = observation name, `ResultStatus`, `AbnormalFlags`) → typed value
  subtables, each 1:1 on `PerformedActID`: **`_TextObservation`** (1.27M), **`_QuantitativeObservation`**
  (62,857), **`_CVObservation`** (28,013, coded), `_DateTimeRangeObservation`, `_EnumObservation`,
  `_BooleanObservation`, `_TextBattery` (27,844, the panel/grouping result). *Gotcha:* "observation
  value" lives in a **different subtable per type** — the agent must UNION/COALESCE across them, not
  read one column. ("many tables are candidates for a base table.")
- **Observation date:** `PerformedActs.ActivityTime_StartDateTime` (also Effective/Created/Modified
  ranges — the *_HasTime/_StartDateTime/_EndDateTime triplets are another gotcha; ActivityTime is the
  clinically-correct one).
- **Parent-observation grouping:** via **`BaseEntityPerformedActs`** (1,391,478 rows: `PerformedActID →
  PerformedActs`, `ParentID → BaseEntities.EntityID`). Observations attach to a parent **`BaseEntities`**
  (the form/group entity). Grouping "by parent observation where it exists" = group by that
  `ParentID`/EntityID. (Batteries: `_TextBattery` rows are themselves parent observations of their
  member observations — "groupings are just another observation.")
- **Patient MRN (gotcha — not a column):** subjects are `BaseEntities_Subject` (3,524, EntityID inherits
  BaseEntities). MRN is an **entity identifier**: `BaseEntityIdentifiers` (`ParentID` = subject EntityID,
  `IdentifierID`) → **`Identifiers`** (`IdentifierValue`, `IdentifierCodeID`) → filter
  **`IdentifierCodeID = 3017399`** (`CV_IdentifierCode.Code='MRN'`; 3,495 patients have one). The
  denormalized `A_*_CRIS` report tables expose a flat `MRN` column but are out-of-scope naive sources.
- **User who locked the record (gotcha):** **`BaseEntityStates`** (form-state transition history:
  `SourceID → BaseEntities.EntityID`, `FormStateID → CVs_FormState`, `UserID → Users.ID` [54 users:
  First/LastName/AccountName], `ExistenceTime_StartDateTime` = when, `Reason`). *Locked* =
  `FormStateID IN (1000023 'Complete'→"Locked", 1000024 'Approved'→"Locked - Approved")` per
  `CV_FormState` (IsEditable=false rows). The locking user = the `BaseEntityStates` row that moved the
  observation's entity into a locked form-state; **nullable** ("if record was locked"). Observations
  link to their state-bearing entity via the `BaseEntityPerformedActs.ParentID`/`BaseEntities` spine.
- **Naive views:** `CV_*` views decode coded values (used above for the oracle); the task forbids using
  the slow pre-built report views *as the query source* but allows reading them for structure.

**Scoring:** judge scores against this path for the four gotchas — (1) SCD-II current-version filter,
(2) parent grouping via BaseEntityPerformedActs/BaseEntities, (3) per-type value subtable union, (4)
locked-by-user via BaseEntityStates+CVs_FormState — plus MRN-as-identifier. Query-shape variation
allowed. Reference: user has analogous SSRS queries (asterisk on oracle independence).

> **Run-readiness (2026-06-03):** **B1 + B2 + B3 oracles ALL COMPLETE.** MSSQL reachable after `kinit`
> (conn `437307010365`, transient). No executors spawned yet (paused per user before run).

## Phase B — RUN OUTCOMES (executed 2026-06-03, against fixed code)

**Method:** 5 blind executors (B1 ⚖ ×2 arms, B2 ×1, B3 ⚖ ×2 arms), each given persona + verbatim
task + exactly one toolset, blind to the eval/oracle/gotchas. Then 3 unlabeled judges (arms relabeled
Submission A/B in mixed order, judges blind to which arm was tool-under-test vs raw SQL; orchestrator
held the de-anon map and did the tool-utility synthesis). dbmcp-test ran the UE-fixed code throughout.

**De-anonymization (orchestrator-private during judging):**
- B1: A = `databricks` raw-SQL arm · B = dbmcp-test arm.
- B3: A = dbmcp-test arm · B = MSSQL raw-via-`execute_query` arm.
- B2: single submission = dbmcp-test arm.

### Scorecard

| Task | dbmcp-test arm | raw-SQL arm | Judge verdict (vs oracle) |
|------|----------------|-------------|---------------------------|
| **B1** ⚖ | **WON decisively** — found BOTH sources (Cerner 111,307 + Epic 71,273) | **LOST** — declared "Cerner has no usable micro data / empty scaffolding," delivered Epic-only; **factually wrong**, missed ~101K Cerner results | tool arm correct on the decisive source-coverage axis |
| **B2** | **5/5 all axes** | (no ⚖) | cleared both traps; honest confidence calibration |
| **B3** ⚖ | **WON 5.0 vs 3.0** — used `ClonedFromID` current-version filter; grappled with the clone/locked-copy lock subtlety | **LOST** — used `IsArchived=0` (wrong: only 10 rows archived → excludes ~0 prior versions); missed lock subtlety | tool arm correct on the decisive prior-version axis |

> ⚠ **The scorecard does NOT establish tool causation.** "Tool arm won" is a per-instance outcome
> (n=1/arm), not evidence the tools *caused* the better answers. The transcript-level post-hoc below
> ("token cost + reasoning-trajectory analysis") shows both decisive wins came from steps available to
> *both* arms, and that the tool arms carried a real round-trip token cost. Read that section before
> quoting this table.

### Reading the results (honest confounds)

- **Headline: in both ⚖ tasks the dbmcp-test arm produced the more correct answer, and B2 was flawless.**
  No tool output misled an executor in Phase B (contrast Phase A, where tools returned null/empty/wrong
  and SQL-fluent agents routed around them). The UE fixes held: B1/B2 exercised `find_fk_candidates`
  (UE-01) and `get_column_info` distinct (UE-03) at scale with no crash and no misleading output; the
  modulo fix (UE-04) wasn't directly exercised.
- **Confound (stated plainly): n=1 per arm.** Each ⚖ cell is a single executor transcript, so the
  head-to-head outcome blends *tool effect* with *executor reasoning variance*. The wins are real but
  are **not** clean evidence that the tools *caused* the better answer — a different raw-SQL executor
  might have found Cerner micro (B1) or used `ClonedFromID` (B3). What IS clean: (a) the tools did not
  mislead, (b) B2's correctness + honesty under the fixed `find_fk_candidates`, (c) the tool arm never
  lost.
- **Why the raw arms lost (mechanism, not tool-credit):** B1-raw stopped one join short — it found
  `ce_microbiology` (51,361 rows) but never joined it back to `clinical_event` + `code_value` +
  `person_alias`, then generalized "empty scaffolding" from the genuinely-empty `dw_*`/`edw_f_*` stubs.
  B3-raw actively reasoned *against* the correct `ClonedFromID` filter ("clones aren't necessarily prior
  versions; use IsArchived") and self-documented the tell ("only 10 archived… filter changes little").
  Both are reasoning errors the structured toolset's defaults happened to steer the other arm away from.
- **B2 prsnl quirk validated UE-adjacent design:** the executor's first `get_sample_data` assuming
  `PRSNL_ID` errored and *revealed* the real PK is `PERSON_ID` — a tool error that was diagnostic rather
  than misleading. No new finding; logged as a positive.

### New findings / dispositions

- **No new UE-class defects.** Phase B surfaced no misleading-output bug in the fixed tools. The three
  UE fixes are corroborated as effective under realistic open-ended load.
- **B1 cross-schema MRN bridge** (oracle's flagged open bridge): the tool arm correctly sourced MRN from
  `v500.person_alias` (alias type 2448) when the MV's usual crosswalk was out of scope — the confined
  harder path worked. No tool gap.
- **Observation (not a defect):** neither B1 arm matched the reference row totals exactly (tool arm
  182,580 vs ref 238,978, mainly from excluding Epic `MOLECULAR MICROBIOLOGY`; raw arm 358,016 Epic-only).
  Open-ended scope variance, expected for a no-exact-match task; judge scored path/grain/DQ, not row count.

### Post-hoc: token cost + reasoning-trajectory analysis (transcript-level, 2026-06-03)

Prompted by the observation that the tool arms used *more* tokens (B1 ≈ even 109k/105k; B3 130k vs 94k,
+39%) — does the toolset help, tax, or shape reasoning? Parsed the 5 executor transcripts for token
**decomposition** (not just totals) and traced the **decisive fork** in each ⚖ task.

**Token decomposition (per arm):**

| Arm | total | asst turns | tool calls | out tok | TR chars/call | raw `execute_query` calls |
|-----|-------|-----------|-----------|---------|---------------|---------------------------|
| B1-dbmcp | 108,986 | 42 | 30 | 12,267 | 2,882 | 20 |
| B1-raw | 105,477 | 37 | 25 | 6,106 | **3,465** | 25 (only tool) |
| B3-dbmcp | 130,328 | 96 | 65 | 18,087 | 1,159 | 35 |
| B3-raw | 93,690 | 56 | 35 | 14,078 | 994 | 35 (only tool) |

- **NOT an envelope tax.** Tool-result chars/call were comparable; in B1 the raw arm's payloads were
  *larger* (3,465 vs 2,882) — raw SELECTs return data rows, structured calls return lean metadata. The
  "verbose wrapper" mechanism is not what inflated tokens.
- **Cost mechanism = atomic-discovery round-trips, not payload.** B3-dbmcp ran ≈ the *same* number of raw
  `execute_query` calls as B3-raw (35 ≈ 35) and layered ~30 single-object structured calls on top
  (`list_tables` ×13, `get_table_schema` ×15). Because the discovery tools are **one-object-per-call**,
  exploring N tables = N round-trips, each re-reading a growing context (B3-dbmcp cache-read 7.6M vs
  3.6M). A SQL-fluent agent batches that into a couple of `INFORMATION_SCHEMA`/`SHOW` queries. **This is
  a real efficiency knock against the structured discovery tools specifically (`list_tables` /
  `get_table_schema` / `get_sample_data`) for the SQL-fluent audience.** B1 masked it only because the
  raw arm's fat data-SELECTs offset the dbmcp arm's extra metadata calls.

**Decisive-fork trace (does the toolset cause the better answer?):**
- **B3 (`ClonedFromID` vs `IsArchived`):** BOTH arms read the off-limits view via the *same* raw
  `sys.sql_modules` query. B3-raw stopped at the view's **archived branch** (`FormStateID=1001208 AND
  IsArchived=1`) and anchored on `IsArchived` (even argued *against* `ClonedFromID`). B3-dbmcp read
  **further into the same view** to its primary branch (`WHERE PA.ClonedFromID IS NULL`), then verified
  empirically. **Decisive step used a tool common to both arms** — winner read more + verified harder.
- **B1 ("Cerner empty" miss):** B1-dbmcp's winning pivot was a *domain-knowledge* statement at turn 3,
  **before any differentiating tool output** ("v500 Millennium micro lives in `clinical_event` + extension
  tables; EVENT_ID is the join key"). B1-raw saw the same `EVENT_ID` columns in `ce_microbiology`, judged
  it not worth the code-value joins, **never looked at `clinical_event`**, and generalized "empty" from the
  genuinely-empty `dw_*` stubs. The pivot was prior knowledge, not a tool affordance.

**Verdict on the three hypotheses:**
- **H-envelope-tax (tools inflate via verbose output): REFUTED.** Payloads comparable / raw larger.
- **H-roundtrip-cost (atomic discovery tools cost extra turns): SUPPORTED.** +39% on B3 traced to ~30
  single-object discovery calls layered atop identical raw-SQL work. Real cost for SQL-fluent users.
- **H-tool-improved-quality (tools uniquely enabled the wins): NOT SUPPORTED.** Both decisive insights
  came from steps available to both arms (shared raw view-read; pre-tool domain knowledge). No transcript
  shows a *structured-tool output* delivering information raw SQL couldn't, that flipped a conclusion.
- **Confound, stated precisely:** in B3 the extra tokens and the better answer are the *same variable* —
  investigation depth (B3-dbmcp investigated ~1.85×). Weak/indirect evidence that atomic tools *nudge* a
  multi-turn list→describe→sample→query rhythm (→ more depth → better answer), but with n=1/arm this is
  indistinguishable from one instance simply being more diligent. **No clean tool-credit story survives.**

**Sharpened conclusion:** the most defensible reading is *not* "tools helped." It is: **the structured
discovery tools did not mislead and did not uniquely help, and they carry a measurable round-trip token
cost for SQL-fluent agents.** The genuine value case for the toolset remains the Phase-A finding (tools
must not return null/empty/wrong — a tool that forces a confirmatory query is net-slower than the query),
plus the UE fixes that removed the misleading outputs. The accelerator case for SQL-fluent users is, on
this evidence, unproven and somewhat counter-indicated on token cost.

> **Phase B COMPLETE (2026-06-03).** Tool-under-test arm won or tied every task; B2 flawless; no
> misleading output; no new defects. **Token/fork post-hoc:** envelope-tax refuted; atomic-discovery
> round-trip cost confirmed (B3 +39%); tool-improved-quality unsupported (decisive forks used shared
> steps); wins confounded with investigation depth (n=1/arm). UE-01/03/04 fixes corroborated under
> realistic load. Utility eval (Phase A + B) concluded.
