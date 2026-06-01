---
phase: quick-260529-jwa
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/analysis/_sql.py
  - src/analysis/fk_candidates.py
  - src/analysis/pk_discovery.py
  - tests/unit/test_analysis_sql.py
  - tests/unit/test_fk_candidates.py
  - tests/unit/test_pk_discovery.py
autonomous: true
requirements: [WR-03]

must_haves:
  truths:
    - "On the cross-catalog Databricks branch, FK get_candidate_columns(all-columns) and PK _list_all_columns report the SAME reflected is_nullable for a given column (sourced from {catalog}.information_schema.columns, not fabricated)."
    - "A column that is declared is_nullable=YES but is empirically unique over its data STILL surfaces as a structural PK candidate on the cross-catalog branch (the all-nullable-table regression guard)."
    - "The default-catalog, MSSQL, and generic/Inspector nullability paths are byte-identical to before (no behavioral change)."
    - "reflect_columns and its existing callers/tests are unchanged."
  artifacts:
    - path: "src/analysis/_sql.py"
      provides: "New CatalogAwareReflector.reflect_column_nullability returning a name->is_nullable(bool) map from {catalog}.information_schema.columns"
      contains: "def reflect_column_nullability"
    - path: "src/analysis/fk_candidates.py"
      provides: "Cross-catalog all-columns branch overlays reflected nullability instead of hardcoded True"
    - path: "src/analysis/pk_discovery.py"
      provides: "Cross-catalog _list_all_columns reports reflected nullability while preserving the probe-only structural gate"
  key_links:
    - from: "src/analysis/fk_candidates.py get_candidate_columns(pk_candidates_only=False) cross-catalog branch"
      to: "CatalogAwareReflector.reflect_column_nullability"
      via: "name->is_nullable lookup overlaid onto reflect_columns output"
      pattern: "reflect_column_nullability"
    - from: "src/analysis/pk_discovery.py _list_all_columns cross-catalog branch"
      to: "CatalogAwareReflector.reflect_column_nullability"
      via: "name->is_nullable lookup, reported but NOT fed into the structural gate"
      pattern: "reflect_column_nullability"
---

<objective>
Fix WR-03: the cross-catalog Databricks branch fabricates contradictory nullability defaults for the same column. FK `get_candidate_columns` (all-columns) hardcodes `is_nullable=True`; PK `_list_all_columns` hardcodes `is_nullable=False`. A consumer correlating `find_fk_candidates` and `find_pk_candidates` gets contradictory nullability for one column.

Approach (LOCKED — do not revisit): "Reflect + report, but probe gates."
- Reflect REAL nullability from `{catalog}.information_schema.columns` (verified queryable cross-catalog, unlike `DESCRIBE TABLE`).
- Report it truthfully in BOTH tools so the reflection layer agrees for any given column.
- Preserve the probe-only structural gate: declared nullability is REPORTED but does NOT exclude a column from structural PK candidacy on the cross-catalog branch (cerner_src.v500 has all 114,293 columns declared `is_nullable=YES`; gating on declared nullability would silently delete every structural PK candidate).

Purpose: Eliminate the fabricated, contradictory nullability between the two analysis tools without regressing structural candidacy.
Output: A new catalog-aware nullability reflection method consumed by both tools, with TDD tests proving agreement and the regression guard.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

# WR-03 finding
@.planning/phases/15.1-cross-catalog-metadata-threading-thread-resolved-catalog-thr/15.1-REVIEW.md

# Files to modify
@src/analysis/_sql.py
@src/analysis/fk_candidates.py
@src/analysis/pk_discovery.py

<interfaces>
<!-- Extracted from codebase. Executor should use these directly. -->

CatalogAwareReflector (src/analysis/_sql.py:55-140) — operates over the live
connection the analysis class already holds; never opens a new engine.connect();
never emits USE CATALOG (stateless, T-15.1-04).
  __init__(self, connection: Connection, dialect: DialectStrategy)
  reflect_columns(self, catalog, schema, table) -> list[dict]   # [{"name","data_type"}] — DO NOT MODIFY (callers/tests depend on this exact shape)
  list_tables(self, catalog, schema) -> list[str]

Existing cross-catalog info_schema pattern to MIRROR
(src/analysis/pk_discovery.py:258-276, _get_constraint_candidates_cross_catalog):
  qi = self._dialect.quote_identifier
  info_schema = f"{qi(self._catalog)}.information_schema"   # catalog identifier QUOTED via dialect.quote_identifier (escapes backticks per CR-01)
  text(f"SELECT ... FROM {info_schema}.<table> WHERE table_schema = :schema_name AND table_name = :table_name")
  connection.execute(query, {"schema_name": ..., "table_name": ...})
  # schema/table are STRING LITERALS in the WHERE clause -> bound as :params (correct, preferred). Catalog is an IDENTIFIER -> f-string + quote_identifier.

Cross-catalog gate (both files):
  self._cross_catalog = bool(catalog) and dialect is not None and dialect.name == "databricks"

PK structural gate that MUST NOT receive declared nullability (pk_discovery.py:345-348):
  for col_name, data_type, is_nullable in all_columns:
      if col_name in exclude_columns or is_nullable:   # <-- if reflected YES flows here, all structural candidates vanish on all-nullable tables
          continue
  # structural candidates emit is_non_null=True because _column_is_unique proved non-null over the domain.

FK all-columns cross-catalog branch (fk_candidates.py:270-285): currently hardcodes is_nullable=True.
PK _list_all_columns cross-catalog branch (pk_discovery.py:377-385): currently hardcodes is_nullable=False.

Models (src/models/analysis.py): PKCandidate.is_non_null: bool (line 119);
FKCandidateData.target_is_nullable: bool (line 153). No model changes required.

Test helper (tests/unit/test_pk_discovery.py:682-724) _CatalogDiscriminatingConnection.execute
dispatches on SQL content: returns the PK row only when TABLE_CONSTRAINTS/KEY_COLUMN_USAGE
present AND catalog-qualified; returns [] otherwise; asserts no USE CATALOG.
A new branch is needed to return is_nullable rows when the SQL targets information_schema.columns.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add reflect_column_nullability to CatalogAwareReflector (RED then GREEN)</name>
  <files>src/analysis/_sql.py, tests/unit/test_analysis_sql.py</files>
  <behavior>
    - Given a fake connection whose information_schema.columns returns rows
      [("id","NO"), ("name","YES")], reflect_column_nullability("cat","sch","tbl")
      returns {"id": False, "name": True} (is_nullable mapped from 'YES'/'NO').
    - The executed SQL targets {qi(catalog)}.information_schema.columns, binds
      :schema_name and :table_name as params (NOT interpolated), and emits no USE CATALOG.
    - A 'YES'/'NO' value is matched case-insensitively / trimmed defensively
      (mirror existing `row[2] == "YES"` style but tolerate whitespace).
    - reflect_columns is unchanged (assert its existing tests still pass).
  </behavior>
  <action>
    Add method `reflect_column_nullability(self, catalog, schema, table) -> dict[str, bool]`
    to CatalogAwareReflector. Mirror the existing cross-catalog info_schema pattern from
    pk_discovery._get_constraint_candidates_cross_catalog: build
    `info_schema = f"{self.dialect.quote_identifier(catalog)}.information_schema"`, then
    `text(f"SELECT column_name, is_nullable FROM {info_schema}.columns WHERE table_schema = :schema_name AND table_name = :table_name")`,
    executed with bound params `{"schema_name": schema, "table_name": table}`. Return a dict
    mapping column_name -> (is_nullable string strip().upper() == "YES"). Do NOT add USE CATALOG.
    Do NOT modify reflect_columns. Add a docstring noting DESCRIBE TABLE cannot provide nullability,
    so information_schema.columns is the source (catalog-scoped, identifier quoted; schema/table bound).
    Write the failing test in tests/unit/test_analysis_sql.py FIRST using the same fake-connection
    style already present in that file; confirm RED, then implement to GREEN.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_analysis_sql.py -x -q</automated>
  </verify>
  <done>reflect_column_nullability returns a correct name->bool map from a fake information_schema.columns; no USE CATALOG emitted; schema/table bound as params; reflect_columns tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Report reflected nullability in both tools; preserve probe-only structural gate (RED then GREEN)</name>
  <files>src/analysis/fk_candidates.py, src/analysis/pk_discovery.py, tests/unit/test_fk_candidates.py, tests/unit/test_pk_discovery.py</files>
  <behavior>
    - AGREEMENT TEST: Given a fake cross-catalog connection where column "patient_id"
      is reflected as is_nullable=YES via information_schema.columns, FK
      get_candidate_columns(pk_candidates_only=False) reports is_nullable=True for
      "patient_id" AND PK _list_all_columns reports the SAME is_nullable for "patient_id".
      (Both sourced from reflect_column_nullability — no fabricated default.)
    - REGRESSION GUARD: Given a cross-catalog column declared is_nullable=YES whose
      uniqueness probe (_column_is_unique) returns True, get_structural_candidates STILL
      emits it as a structural PK candidate with is_non_null=True. (Declared nullability
      must NOT reach the structural gate; the probe is the sole gate.)
    - A column reflected is_nullable=NO is reported is_nullable=False by FK and PK reflection layers.
    - DEFAULT-PATH UNCHANGED: catalog=None / MSSQL / Inspector paths produce identical
      nullability output to before (extend or reuse existing tests asserting this).
  </behavior>
  <action>
    FK get_candidate_columns (cross-catalog all-columns branch, ~270-285): after reflect_columns,
    call reflect_column_nullability(self._catalog, target_schema, target_table) and overlay the
    reflected value as is_nullable (default to True only if a column is absent from the map — a
    defensive fallback, not the primary behavior). Replace the hardcoded `is_nullable=True`.

    PK _list_all_columns (cross-catalog branch, ~377-385): call reflect_column_nullability for the
    target table and return the REFLECTED is_nullable in the tuple's third slot for REPORTING.
    HOWEVER, get_structural_candidates' gate at line 347 (`if col_name in exclude_columns or is_nullable: continue`)
    must NOT exclude columns based on declared nullability on the cross-catalog branch. Implement this
    by having get_structural_candidates skip the `is_nullable` half of the gate when self._cross_catalog
    is True (the _column_is_unique probe remains the sole structural gate; emitted candidates keep
    is_non_null=True because the probe proved non-null over the domain). On the default/Inspector/MSSQL
    branches the gate stays exactly as-is (is_nullable still excludes). Do NOT change the constraint
    cross-catalog path (_get_constraint_candidates_cross_catalog) — its semantics are correct.

    Extend the test fakes: in tests/unit/test_pk_discovery.py add an information_schema.columns branch
    to _CatalogDiscriminatingConnection (or a focused fake) returning is_nullable rows; in
    tests/unit/test_fk_candidates.py use the existing catalog-discriminating fake pattern. Write the
    AGREEMENT and REGRESSION-GUARD tests FIRST (RED), then implement to GREEN.

    Comment/docstring updates: replace the now-stale "treat as nullable so no candidate is falsely
    excluded" (fk_candidates.py:276-277) and "treat reflected columns as non-nullable" (pk_discovery.py:378-380)
    comments to describe the reflect-and-report + probe-only-gate design.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_fk_candidates.py tests/unit/test_pk_discovery.py -x -q</automated>
  </verify>
  <done>FK and PK reflection layers report the SAME reflected is_nullable for a given cross-catalog column; a declared-nullable-but-probe-unique column still surfaces as a structural PK candidate; default/MSSQL/Inspector paths unchanged.</done>
</task>

<task type="auto">
  <name>Task 3: Full suite + lint gate</name>
  <files>(no source changes — verification only; fix any fallout in the files above)</files>
  <action>
    Run the full unit suite with coverage and the linter. The 6 Azure AD integration tests in
    test_azure_ad_auth.py fail environmentally (live Azure SQL unreachable) — NOT a regression,
    NOT in scope; treat the rest of the suite as the correctness gate. Ensure coverage stays at or
    above the 85% floor (--cov-fail-under enforced by project config) and zero new ruff warnings
    (the pre-existing src/metrics.py Generator-import warning is known and out of scope). If anything
    breaks, fix within the files modified by Tasks 1-2.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/ -q && uv run ruff check src/analysis/</automated>
  </verify>
  <done>Full unit suite green (excluding the known-environmental Azure AD integration failures), coverage >= 85%, no new ruff warnings in src/analysis/.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller -> analysis SQL | catalog/schema/table values flow into cross-catalog reflection SQL |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-WR03-01 | Tampering/Injection | reflect_column_nullability {catalog}.information_schema.columns query | mitigate | catalog identifier quoted via dialect.quote_identifier (escapes backticks per CR-01); schema/table bound as :params, never interpolated |
| T-WR03-02 | Tampering | session catalog state | mitigate | No USE CATALOG emitted; fully-qualified stateless query over pooled connection (T-15.1-04); test asserts absence |
| T-WR03-SC | Tampering | npm/pip/cargo installs | accept | No new dependencies added |
</threat_model>

<verification>
- reflect_column_nullability sources nullability from information_schema.columns (not DESCRIBE TABLE), with the catalog quoted and schema/table bound.
- For any cross-catalog column, FK get_candidate_columns(all-columns) and PK _list_all_columns report identical is_nullable.
- A declared-nullable, probe-unique cross-catalog column still appears as a structural PK candidate (is_non_null=True).
- Default-catalog / MSSQL / Inspector nullability handling is unchanged.
- reflect_columns and its callers/tests are untouched.
</verification>

<success_criteria>
- WR-03 contradiction eliminated: the reflection layer reports the same truthful nullability across both tools.
- No regression in structural PK candidacy on all-nullable cross-catalog tables.
- Full unit suite green (excluding known-environmental Azure AD integration failures); coverage >= 85%; no new ruff warnings.
</success_criteria>

<output>
Create `.planning/quick/260529-jwa-fix-wr-03/260529-jwa-SUMMARY.md` when done.
</output>
