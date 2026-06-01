---
phase: quick-260528-qcp
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/test_query.py
  - src/db/query.py
autonomous: true
requirements: [SC3]

must_haves:
  truths:
    - "get_sample_data with a real dialect and schema_name=None builds an unqualified table reference (no 'None.' segment, no AttributeError)"
    - "The existing MSSQL 2-part (schema.table) path is unchanged when schema_name is provided"
    - "The existing Databricks 3-part (catalog.schema.table) path is unchanged when catalog and schema_name are provided"
  artifacts:
    - path: "src/db/query.py"
      provides: "Schema-guarded full_table_name construction in get_sample_data"
      contains: "if schema_name:"
    - path: "tests/unit/test_query.py"
      provides: "Real-dialect regression test for None schema in get_sample_data"
  key_links:
    - from: "src/db/query.py get_sample_data else branch"
      to: "dialect.quote_identifier"
      via: "schema_name presence guard"
      pattern: "if schema_name"
---

<objective>
Fix the Phase 15 SC3 blocker: `get_sample_data` builds a corrupt table reference when the resolved schema is `None`.

When a non-MSSQL dialect has `default_schema=None` (generic, or Databricks without an explicit schema), `schema_name` reaches `get_sample_data` as `None`. The `else` branch unconditionally calls `self._dialect.quote_identifier(schema_name)`, which calls `.replace()` on `None` → uncaught `AttributeError` (all three real dialects), and would otherwise produce a `"None"."table"` reference if quoting were lenient. Removing the hardcoded `dbo` default (SC4) exposed this previously-masked call site. The existing `test_get_sample_data_none_schema_builds_unqualified_reference` only exercises the `self._dialect is None` (SQLite) branch, so it never touched the real-dialect path.

Purpose: Close the single verification blocker so Phase 15 SC3 (cross-dialect identifier resolution) passes.
Output: A guarded `full_table_name` construction plus a real-dialect regression test.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.planning/phases/15-unified-identifier-resolver-cross-dialect/15-VERIFICATION.md

<interfaces>
<!-- Contracts the executor needs. Already extracted — no codebase exploration required. -->

QueryService constructor (src/db/query.py:50):
  QueryService(engine, metadata_service=None, dialect: DialectStrategy | None = None)
  - When dialect is passed, self._dialect = dialect (no engine inference).

Dialect classes (src/db/dialects/__init__.py):
  from src.db.dialects import GenericDialect, MssqlDialect, DatabricksDialect
  - GenericDialect.default_schema -> None;  quote_identifier(x) -> f'"{x.replace(...)}"' (ANSI double-quote)
  - MssqlDialect.default_schema  -> "dbo";  quote_identifier(x) -> f'[{x.replace("]","]]")}]'
  - DatabricksDialect: max_identifier_depth = 3; quote_identifier uses backticks
  - All three call .replace() on the identifier, so quote_identifier(None) raises AttributeError.

Current code under repair (src/db/query.py get_sample_data, ~lines 119-133):
  - if self._dialect is None:        full_table_name = table_name              # SQLite/no-dialect path
  - elif catalog and name=="databricks":  catalog.schema.table (3 quoted segments)
  - else:                            f"{quote_identifier(schema_name)}.{quote_identifier(table_name)}"   # BUG: schema_name may be None

table_id construction already handles None correctly (query.py:174):
  table_id = f"{schema_name}.{table_name}" if schema_name else table_name

Existing test that only covers the _dialect is None branch:
  tests/unit/test_query.py:1061  test_get_sample_data_none_schema_builds_unqualified_reference
  (class TestSampleDataSchemaDefault, uses the mock_engine fixture and a fake_execute that captures the SQL)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — real-dialect regression test for None schema in get_sample_data</name>
  <files>tests/unit/test_query.py</files>
  <behavior>
    Add to class TestSampleDataSchemaDefault (after the existing none_schema test, ~line 1093):
    - test_get_sample_data_none_schema_real_generic_dialect_unqualified:
        Construct QueryService(mock_engine, dialect=GenericDialect()) and call
        get_sample_data(table_name="Customers", schema_name=None, sample_size=5,
        sampling_method=SamplingMethod.TOP). Capture the executed SQL via a
        fake_execute side_effect (mirror the existing test's pattern at lines 1068-1078).
        Assert: no AttributeError is raised; the captured SQL contains the quoted
        bare table ("Customers" / '"Customers"') and contains NO 'None.' segment
        and NO 'None"."' / '"None"' schema artifact; sample.table_id == "Customers".
    - test_get_sample_data_mssql_two_part_reference_preserved (guard against regression):
        QueryService(mock_engine, dialect=MssqlDialect()),
        get_sample_data(table_name="Customers", schema_name="sales", ...).
        Assert captured SQL contains "[sales].[Customers]" — the 2-part path is intact.
    Import GenericDialect and MssqlDialect from src.db.dialects at the top of the test
    (or locally inside the test functions, matching file convention).
  </behavior>
  <action>Write the two tests per the behavior block. Reuse the existing fake_execute capture pattern from test_get_sample_data_none_schema_builds_unqualified_reference (returns a MagicMock whose __iter__ yields []). The generic-dialect test is the RED test — it MUST fail before Task 2 because quote_identifier(None) raises AttributeError. The MSSQL test should already PASS (it exercises the existing, correct 2-part path) and acts as a no-regression guard. Do NOT inline production code into the test; only construct dialects and assert on captured SQL.</action>
  <verify>
    <automated>uv run pytest tests/unit/test_query.py::TestSampleDataSchemaDefault::test_get_sample_data_none_schema_real_generic_dialect_unqualified -x 2>&1 | grep -q "AttributeError\|FAILED" && echo RED_CONFIRMED</automated>
  </verify>
  <done>New generic-dialect test fails with AttributeError (RED). New MSSQL test passes. Tests added inside TestSampleDataSchemaDefault.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — guard the else branch on schema_name presence</name>
  <files>src/db/query.py</files>
  <behavior>
    After the fix, the get_sample_data else branch produces:
    - schema_name present: f"{quote_identifier(schema_name)}.{quote_identifier(table_name)}" (unchanged 2-part)
    - schema_name None/empty: quote_identifier(table_name) only (unqualified, no leading 'None.')
    Databricks 3-part elif (catalog and name=="databricks"): when schema_name is None
    but catalog is present, the schema segment must NOT emit quote_identifier(None).
  </behavior>
  <action>In src/db/query.py get_sample_data, change the `else` branch (currently ~line 132-133) so that the schema segment is only emitted when schema_name is truthy: when schema_name is present, keep the existing two-part `f"{self._dialect.quote_identifier(schema_name)}.{self._dialect.quote_identifier(table_name)}"`; otherwise build `self._dialect.quote_identifier(table_name)` alone. Also harden the Databricks 3-part `elif catalog and self._dialect.name == "databricks"` branch (~lines 123-131): inspect the current 3-part construction and ensure quote_identifier is not called on a None schema_name — when schema_name is None build a `catalog.table` reference (quoted catalog segment + quoted table) rather than `catalog.None.table`; confirm the cross-catalog reference shape against the existing branch rather than assuming a fixed string. This closes the SC3 blocker exposed when the SC4 'dbo' default was removed (verifier-suggested fix). Preserve quote_identifier on every emitted segment — it remains the injection defense; do not raw-concat identifiers.</action>
  <verify>
    <automated>uv run pytest tests/unit/test_query.py::TestSampleDataSchemaDefault -x 2>&1 | tail -3</automated>
  </verify>
  <done>All TestSampleDataSchemaDefault tests pass (RED test now GREEN). The else branch emits an unqualified reference when schema_name is falsy; 2-part MSSQL path unchanged; Databricks branch no longer calls quote_identifier(None).</done>
</task>

<task type="auto">
  <name>Task 3: Full regression + lint guard</name>
  <files>src/db/query.py, tests/unit/test_query.py</files>
  <action>Run the full test_query.py module plus ruff to confirm no regression in the Databricks 3-part path, the MSSQL 2-part path, or the SQLite no-dialect path, and zero new lint warnings introduced by this change (per CLAUDE.md: zero warnings before complete). Do not modify behavior in this task; it is a verification gate.</action>
  <verify>
    <automated>uv run pytest tests/unit/test_query.py 2>&1 | tail -3 && uv run ruff check src/db/query.py tests/unit/test_query.py 2>&1 | tail -3</automated>
  </verify>
  <done>Entire tests/unit/test_query.py passes; ruff reports no new warnings on the two touched files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP caller → get_sample_data | table_name/schema_name/catalog are caller-supplied identifiers |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-qcp-01 | Tampering | get_sample_data full_table_name construction | mitigate | Every emitted identifier segment is quoted via dialect.quote_identifier (escapes `]`/`"`/backtick); the fix keeps all segments quoted and only changes whether the schema segment is emitted — no raw string concatenation of caller input is introduced |
| T-qcp-02 | Information Disclosure | None-schema querying wrong namespace | mitigate | Guard ensures an absent schema yields an unqualified reference (engine default namespace) instead of a synthetic `"None"` schema that could silently target an unintended object |
</threat_model>

<verification>
- RED confirmed in Task 1 (AttributeError on generic dialect, None schema).
- GREEN confirmed in Task 2 (unqualified reference, no AttributeError, no `None.` segment).
- No-regression confirmed in Task 3 (full module + ruff).
- Manual cross-check: SC3 blocker in 15-VERIFICATION.md is the only gap this plan targets.
</verification>

<success_criteria>
- `uv run pytest tests/unit/test_query.py` passes (including 3 tests in TestSampleDataSchemaDefault).
- get_sample_data with a real dialect + schema_name=None returns a SampleData with table_id == table_name and a built query containing no `None.` qualifier and no raised AttributeError.
- MSSQL 2-part and Databricks 3-part paths unchanged.
- `uv run ruff check` clean on touched files.
</success_criteria>

<output>
Create `.planning/quick/260528-qcp-fix-phase-15-sc3-blocker-get-sample-data/260528-qcp-SUMMARY.md` when done.
</output>
