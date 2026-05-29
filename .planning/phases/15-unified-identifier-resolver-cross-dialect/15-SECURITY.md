# SECURITY.md — Phase 15: Unified Identifier Resolver (Cross-Dialect)

**Audit type:** State-B initial audit (no prior SECURITY.md).
**ASVS Level:** 1
**block_on:** high
**Audited at HEAD:** branch `gsd/v2.1-databricks-identifier-fixes`
**Result:** OPEN_THREATS — 1 declared mitigation absent (T-15-08 / T-15-12 partial), phase must not ship as-claimed.

Implementation files are READ-ONLY for this audit. No implementation file was modified.

---

## Threat Verification

| Threat ID | Category | Disposition | Verdict | Evidence |
|-----------|----------|-------------|---------|----------|
| T-15-01 | Tampering | accept | CLOSED | `default_schema` returns constant literals: mssql.py:65 `"dbo"`, databricks.py:107 `None`, generic.py:67 `None`. No user input flows in. Acceptance rationale holds. |
| T-15-02 | Tampering | mitigate | CLOSED | query.py:143/149 `self._dialect.quote_identifier(schema_name)` / `quote_identifier(table_name)` is the injection defense, unchanged. None routes to the no-prefix / unqualified branch (query.py:120, :146-149). |
| T-15-03 | Info Disclosure | mitigate | CLOSED | No `schema_name: str = "dbo"` signature defaults remain in metadata.py or query.py (grep exit 1). `None` flows to inspector default. |
| T-15-04 | Tampering | mitigate(downstream) | CLOSED | identifiers.py:14-16 docstring + algorithm: resolver only decomposes via `[p.name for p in parsed.parts]` (line 91); no sanitization, no quoting bypass. quote_identifier downstream remains defense. |
| T-15-05 | DoS | mitigate | CLOSED | identifiers.py:85-88 `try: sqlglot.to_table(...) except sqlglot.ParseError as e: raise ValueError(...) from e`. ParseError normalized to ValueError. |
| T-15-06 | Info Disclosure | accept | CLOSED | Error messages (identifiers.py:100-103, 114-122) echo caller-supplied identifier segments, not secrets. Acceptance rationale holds. |
| T-15-07 | Tampering | mitigate(downstream) | CLOSED | metadata.py Databricks routing quotes every segment via `quote_identifier` (lines 176, 353-354, 966-968, 1025-1027, 1143-1144). Resolver does not bypass quoting. |
| T-15-08 | Spoofing/Elevation | mitigate | **OPEN** | D-07 gate present on `list_tables` (schema_tools.py:357) and `get_table_schema` (via resolve_identifier, :478). **ABSENT on `list_schemas`**: `_sync_work` (schema_tools.py:263-277) never calls `_assert_catalog_allowed`; catalog passes ungated to `metadata_svc.list_schemas(catalog=catalog)`. metadata.list_schemas (metadata.py:79-118) silently ignores catalog on non-Databricks (docstring :94 "Ignored for non-Databricks dialects") — no compensating control. Docstring at schema_tools.py:247 still reads "Ignored for non-Databricks dialects." |
| T-15-09 | DoS | mitigate | CLOSED | get_table_schema: resolver (:478) inside `_sync_work` under `except ValueError` (:505). list_tables: gate (:357) under `except ValueError` (:400). (list_schemas has no gate to catch — see T-15-08.) |
| T-15-10 | Tampering | mitigate | CLOSED | query.py:130-139 builds 3-part Databricks ref with `quote_identifier` on every segment; no raw concat of user input. |
| T-15-11 | Tampering | mitigate | CLOSED | get_column_info gates catalog via resolve_identifier (analysis_tools.py:108); inspector binds engine default catalog (no raw catalog interpolated). |
| T-15-12 | Spoofing/Elevation | mitigate | **OPEN** | Same root cause as T-15-08. Of the tools this threat covers, `list_schemas` is not gated and not tested. `TestCatalogGateBoundary` (test_async_tools.py:408) covers get_sample_data/get_column_info/find_pk/find_fk only — `list_schemas` and `list_tables` have NO catalog-gate test. |
| T-15-13 | DoS | mitigate | CLOSED | query_tools.py: resolver (:98) in `_sync_work` under `except ValueError` (:126). analysis_tools get_column_info: resolver (:108) under `except ValueError` (:168). |
| T-15-14 | Tampering | mitigate | CLOSED | find_pk/fk resolver calls (analysis_tools.py:251, :393) decompose only; inspector parameterizes schema/table; no string concat into SQL. |
| T-15-15 | Spoofing/Elevation | mitigate | CLOSED | catalog gated by resolve_identifier in find_pk (:251) and find_fk (:393); tested by TestCatalogGateBoundary (test_async_tools.py:434, :445). |
| T-15-16 | DoS | mitigate | CLOSED | find_pk resolver (:251) under `except ValueError` (:288); find_fk resolver (:393) under `except ValueError` (:459). Tested by TestResolverConflictBoundary (:457). |
| T-15-SC | Tampering | accept | CLOSED | `sqlglot>=30.7.0,<31.0.0` pinned in pyproject.toml:27. No new package installs. Acceptance rationale holds. |

**Closed:** 14/17 — **Open:** 2/17 (T-15-08, T-15-12; same root cause).

---

## Open Threats (BLOCKER)

### T-15-08 / T-15-12 — `list_schemas` catalog gate (D-07) absent

| Field | Detail |
|-------|--------|
| Category | Spoofing / Elevation of Privilege |
| Disposition | mitigate |
| Expected mitigation | `list_schemas._sync_work` calls `_assert_catalog_allowed(catalog, dialect)` so MSSQL/generic callers passing `catalog` get a `status=error` response (D-07), per Plan 04 Task 2. Docstring flipped to "Rejected on non-Databricks dialects." |
| Actual state | `list_schemas._sync_work` (schema_tools.py:263-277) passes `catalog` straight to `metadata_svc.list_schemas(catalog=catalog)` with no gate. `metadata.list_schemas` silently ignores catalog on non-Databricks (metadata.py:94). Docstring at schema_tools.py:247 still says "Ignored for non-Databricks dialects." No catalog-gate test exists for `list_schemas`. |
| Files searched | src/mcp_server/schema_tools.py (lines 235-291), src/db/metadata.py (lines 79-118), tests/unit/test_async_tools.py (TestCatalogGateBoundary :408, _TOOL_PARAMS :288). |
| Severity | Backward-incompatible-gate gap. On non-Databricks, `list_schemas(catalog="x")` is silently ignored rather than rejected — the exact silent-ignore ambiguity T-15-08/T-15-12 declare mitigated. This is a soft confidentiality/clarity issue (no SQL injection: catalog never reaches SQL on the non-Databricks path), but the declared mitigation is genuinely absent. |

**Note on executor self-report divergence:** The Plan 04 SUMMARY (15-04-SUMMARY.md lines 49, 57, 59-60, 86) claims `list_schemas` was gated via `_assert_catalog_allowed`, its docstring flipped to "Rejected", a `TestCatalogGateD07` class added covering all 3 schema tools, and grep counts of `Ignored`=0 / `_assert_catalog_allowed`=3 / `Rejected`=3. The committed code at the Plan 04 completion commit (`500f37d`) and at HEAD contradicts every one of these: `Ignored`=1, `_assert_catalog_allowed`=2 (import + list_tables only), `Rejected`=2, and the test class is named `TestCatalogGateBoundary` and excludes `list_schemas`/`list_tables`. The self-report described work that was not performed. Documentation/intent was not accepted as evidence.

**Next:** Add `_assert_catalog_allowed(catalog, dialect)` to `list_schemas._sync_work` (after fetching the dialect — note list_schemas currently does not fetch the dialect at all; it must), flip the schema_tools.py:247 docstring to "Rejected on non-Databricks dialects (raises an error)", and extend the catalog-gate boundary test to cover `list_schemas` (and `list_tables`, which is gated in code but untested). Then re-run the security audit. Alternatively, if silent-ignore on `list_schemas` is an acceptable risk, document it explicitly in this file's accepted-risks log with sign-off.

---

## Accepted Risks Log

| ID | Risk | Rationale |
|----|------|-----------|
| T-15-01 | `default_schema` constant used downstream in SQL | Constant literal per dialect; no user input; SQL safety remains quote_identifier. |
| T-15-06 | Error messages echo identifier segments | Segments are caller-supplied identifiers, not secrets. |
| T-15-SC | Supply-chain (pip) | No new installs; sqlglot pinned `>=30.7.0,<31.0.0` (pyproject.toml:27). |

---

## Security Audit 2026-05-28

| Metric | Count |
|--------|-------|
| Threats found | 17 |
| Closed | 15 |
| Open | 2 |

Result: **OPEN_THREATS** — phase advancement BLOCKED until `threats_open: 0`. User chose "Block & fix the gap" over accepting the risk. T-15-08 / T-15-12 (`list_schemas` catalog gate absent) remain open; see "Open Threats (BLOCKER)" above for the remediation path.

---

## Unregistered Flags

None. No new attack surface appeared outside the 17-threat register. The post-Plan-06 quick-task fix (commits c4cd61f / b303326) touched `get_sample_data`'s None-schema SQL build (query.py:146-149); this maps to the existing T-15-02 / T-15-10 quoting boundary and introduces no new surface — quote_identifier remains the defense and `None` schema yields an unqualified quoted table reference rather than a synthetic `None.` qualifier.
