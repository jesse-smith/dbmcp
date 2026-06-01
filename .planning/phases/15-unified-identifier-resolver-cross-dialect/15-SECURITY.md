# SECURITY.md — Phase 15: Unified Identifier Resolver (Cross-Dialect)

**Audit type:** State-B initial audit (no prior SECURITY.md).
**ASVS Level:** 1
**block_on:** high
**Audited at HEAD:** branch `gsd/v2.1-databricks-identifier-fixes`
**Result:** SECURED — `threats_open: 0`. Initial State-B audit found T-15-08 / T-15-12 OPEN; both remediated on branch and verified CLOSED at HEAD `79a8f18` (see Re-Audit 2026-05-28 below).

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
| T-15-08 | Spoofing/Elevation | mitigate | CLOSED | `list_schemas._sync_work` now fetches the dialect (schema_tools.py:265) and calls `_assert_catalog_allowed(catalog, dialect)` (schema_tools.py:266) before the metadata call. Gate raises `ValueError` (identifiers.py:45-57) when `catalog` truthy and `dialect.max_identifier_depth < 3`; caught at schema_tools.py:286 → `status=error`. Docstring flipped to "Rejected on non-Databricks dialects (raises an error)" (schema_tools.py:247). Verified at HEAD `79a8f18`. |
| T-15-09 | DoS | mitigate | CLOSED | get_table_schema: resolver (:478) inside `_sync_work` under `except ValueError` (:505). list_tables: gate (:357) under `except ValueError` (:400). (list_schemas has no gate to catch — see T-15-08.) |
| T-15-10 | Tampering | mitigate | CLOSED | query.py:130-139 builds 3-part Databricks ref with `quote_identifier` on every segment; no raw concat of user input. |
| T-15-11 | Tampering | mitigate | CLOSED | get_column_info gates catalog via resolve_identifier (analysis_tools.py:108); inspector binds engine default catalog (no raw catalog interpolated). |
| T-15-12 | Spoofing/Elevation | mitigate | CLOSED | `TestCatalogGateBoundary` (test_async_tools.py:408) now covers `list_schemas` (test_async_tools.py:456-463) and `list_tables` (test_async_tools.py:465-472). Both patch `MssqlDialect` via `_patch_cm` (depth < 3), call the tool with `catalog="x"`, and assert `error` + `catalog` in the response — genuinely exercising the gate rejection path. Both pass at HEAD `79a8f18`. |
| T-15-13 | DoS | mitigate | CLOSED | query_tools.py: resolver (:98) in `_sync_work` under `except ValueError` (:126). analysis_tools get_column_info: resolver (:108) under `except ValueError` (:168). |
| T-15-14 | Tampering | mitigate | CLOSED | find_pk/fk resolver calls (analysis_tools.py:251, :393) decompose only; inspector parameterizes schema/table; no string concat into SQL. |
| T-15-15 | Spoofing/Elevation | mitigate | CLOSED | catalog gated by resolve_identifier in find_pk (:251) and find_fk (:393); tested by TestCatalogGateBoundary (test_async_tools.py:434, :445). |
| T-15-16 | DoS | mitigate | CLOSED | find_pk resolver (:251) under `except ValueError` (:288); find_fk resolver (:393) under `except ValueError` (:459). Tested by TestResolverConflictBoundary (:457). |
| T-15-SC | Tampering | accept | CLOSED | `sqlglot>=30.7.0,<31.0.0` pinned in pyproject.toml:27. No new package installs. Acceptance rationale holds. |

**Closed:** 16/17 — **Open:** 0/17. (T-15-08 / T-15-12 closed at HEAD `79a8f18` by branch fix commits c9252df / ed1c0e6 / 79a8f18. Note: register has 16 numbered threats T-15-01..T-15-16 plus T-15-SC = 17 total; all CLOSED.)

---

## Open Threats (BLOCKER)

None. T-15-08 and T-15-12 were remediated on branch `gsd/v2.1-databricks-identifier-fixes` and verified closed at HEAD `79a8f18` (see re-audit below).

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

## Re-Audit 2026-05-28 (HEAD `79a8f18`) — T-15-08 / T-15-12 verification

Targeted re-verification of the two remaining OPEN threats after branch fix commits c9252df (wire D-07 gate into list_schemas), ed1c0e6 (boundary tests for list_schemas/list_tables), 79a8f18 (docs). Implementation files unchanged by this audit.

| Threat ID | Disposition | Verdict | Evidence (committed code at HEAD `79a8f18`) |
|-----------|-------------|---------|---------------------------------------------|
| T-15-08 | mitigate | CLOSED | `list_schemas._sync_work` fetches dialect (schema_tools.py:265) and calls `_assert_catalog_allowed(catalog, dialect)` (schema_tools.py:266) before `metadata_svc.list_schemas`. Gate raises `ValueError` (identifiers.py:52-57), caught at schema_tools.py:286 → `status=error`. Docstring flipped to "Rejected on non-Databricks dialects (raises an error)" (schema_tools.py:247). |
| T-15-12 | mitigate | CLOSED | `TestCatalogGateBoundary` extended: `test_list_schemas_catalog_on_mssql_errors` (test_async_tools.py:456-463) and `test_list_tables_catalog_on_mssql_errors` (test_async_tools.py:465-472). Both patch `MssqlDialect` (depth < 3) via `_patch_cm`, invoke with `catalog="x"`, assert `error` + `catalog` in response. Both PASS at HEAD. |

| Metric | Count |
|--------|-------|
| Threats found | 17 |
| Closed | 17 |
| Open | 0 |

Result: **SECURED** — `threats_open: 0`. Both declared mitigations verified present in committed code via file:line evidence and passing tests; no documentation/intent accepted as proof. Prior Plan 04 self-report divergence resolved: at HEAD `_assert_catalog_allowed` = 3 matches (import + list_tables + list_schemas), `Rejected on non-Databricks` = 3, `Ignored for non-Databricks` = 0 in schema_tools.py.

---

## Unregistered Flags

None. No new attack surface appeared outside the 17-threat register. The post-Plan-06 quick-task fix (commits c4cd61f / b303326) touched `get_sample_data`'s None-schema SQL build (query.py:146-149); this maps to the existing T-15-02 / T-15-10 quoting boundary and introduces no new surface — quote_identifier remains the defense and `None` schema yields an unqualified quoted table reference rather than a synthetic `None.` qualifier.
