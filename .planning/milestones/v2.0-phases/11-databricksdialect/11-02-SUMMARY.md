---
phase: 11-databricksdialect
plan: 02
subsystem: database
tags: [databricks, metadata, catalog, describe-extended, index-gating]

# Dependency graph
requires:
  - phase: 11-databricksdialect
    plan: 01
    provides: DatabricksDialect class, ConnectionManager routing, dialect registry
provides:
  - Catalog-aware metadata queries (list_schemas, list_tables, get_table_schema)
  - DESCRIBE TABLE EXTENDED parsing for Databricks table properties
  - Index gating based on dialect.supports_indexes
  - Three-level Databricks table identifiers (catalog.schema.table)
affects: [future-databricks-features, schema-tools-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns: [catalog-param-threading, dte-section-parsing, capability-flag-gating]

key-files:
  created: []
  modified:
    - src/db/metadata.py
    - src/mcp_server/schema_tools.py
    - tests/unit/test_metadata.py
    - tests/staleness/tool_invoker.py
    - tests/integration/test_discovery.py

key-decisions:
  - "Databricks cross-catalog queries use raw SQL (SHOW SCHEMAS/TABLES IN) rather than Inspector per Pitfall 3"
  - "Index key absent (not empty list) when dialect.supports_indexes is False for clear LLM signal (D-13)"
  - "DTE parsing catches all exceptions (not just SQLAlchemyError) per research Pitfall 1"
  - "_get_metadata_service now passes dialect from ConnectionManager for consistent routing"

patterns-established:
  - "Optional catalog parameter threads through MCP tool -> MetadataService -> raw SQL for Databricks"
  - "DTE section-based parsing: partition section, detail section, key_map for property extraction"
  - "Capability-flag gating: check dialect.supports_indexes before including feature-specific response keys"

requirements-completed: [META-01, META-02, META-03, META-04]

# Metrics
duration: 15min
completed: 2026-04-15
---

# Phase 11 Plan 02: Catalog-Aware Metadata and DESCRIBE EXTENDED Parsing Summary

**Catalog-aware metadata with SHOW SCHEMAS/TABLES raw SQL, DESCRIBE TABLE EXTENDED parsing for owner/storage_format/table_type_detail/created_time/location/partition_columns, and index gating via supports_indexes capability flag**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-15T15:41:20Z
- **Completed:** 2026-04-15T15:56:27Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- list_schemas, list_tables, get_table_schema all accept optional `catalog: str | None` parameter
- Databricks connections with explicit catalog use `SHOW SCHEMAS IN` and `SHOW TABLES IN` raw SQL for cross-catalog queries
- Non-Databricks dialects (MSSQL, generic) ignore catalog parameter completely -- zero regression
- `_parse_databricks_table_properties` parses DESCRIBE TABLE EXTENDED output for owner, storage_format (Provider), table_type_detail (Type), created_time, location, and partition_columns
- Index section omitted entirely (key absent) when `dialect.supports_indexes is False` -- missing key = "not supported" vs empty list = "none exist"
- Databricks table identifiers use three-level `catalog.schema.table` format in `_collect_objects_from_schema`
- DTE parsing failures are gracefully handled (empty dict, warning log) -- never breaks get_table_schema
- All identifiers backtick-quoted via `dialect.quote_identifier()` in raw SQL (T-11-04, T-11-05 mitigations)
- `_get_metadata_service` in schema_tools.py now passes dialect from ConnectionManager for consistent behavior
- 28 new tests, 806 total passing (737 unit + 69 integration/other), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add optional catalog parameter to MCP schema tools and MetadataService methods** - `6552c17` (feat)
2. **Task 2: Add DESCRIBE EXTENDED parsing, index gating, and Databricks table properties** - `281c373` (feat)

_Note: TDD tasks -- tests written first (RED), then implementation (GREEN)._

## Files Created/Modified
- `src/db/metadata.py` - Catalog parameter on list_schemas/list_tables/get_table_schema, _list_schemas_databricks, _list_tables_databricks, _parse_databricks_table_properties, index gating, three-level table IDs
- `src/mcp_server/schema_tools.py` - Optional catalog parameter on all three schema tools, _get_metadata_service passes dialect
- `tests/unit/test_metadata.py` - 28 new tests: TestCatalogListSchemas, TestCatalogListTables, TestCatalogGetTableSchema, TestCatalogThreeLevelTableId, TestIndexGating, TestDescribeExtended, TestDatabricksTableProperties
- `tests/staleness/tool_invoker.py` - Added get_dialect mock to success mock contexts for list_schemas, list_tables, get_table_schema
- `tests/integration/test_discovery.py` - Added get_dialect mock patches with proper PropertyMock dialect

## Decisions Made
- Databricks cross-catalog queries use raw SQL (`SHOW SCHEMAS IN`, `SHOW TABLES IN`) rather than Inspector, because Inspector only supports the catalog set at engine creation time (research Pitfall 3)
- Index key is absent (not empty list) when `dialect.supports_indexes is False` -- provides clearer semantic signal for LLM agents (D-13)
- DTE parsing catches all exceptions (not just SQLAlchemyError) because Databricks connector may raise DB-API exceptions not wrapped by SQLAlchemy (research Pitfall 1)
- `_get_metadata_service` updated to pass dialect from ConnectionManager, ensuring consistent dialect-aware behavior across all schema tools

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Staleness guard tests failed due to missing get_dialect mock**
- **Found during:** Task 1 verification
- **Issue:** `_get_metadata_service` now calls `conn_manager.get_dialect()` which raises ValueError for unmocked connection IDs
- **Fix:** Added `get_dialect` mock patches to staleness tool_invoker success mock contexts
- **Files modified:** tests/staleness/tool_invoker.py
- **Commit:** 6552c17

**2. [Rule 1 - Bug] Integration tests failed due to MagicMock dialect being truthy for has_fast_row_counts**
- **Found during:** Task 2 verification
- **Issue:** Default MagicMock returns truthy for all attribute access, causing MSSQL code path to be taken instead of generic
- **Fix:** Created `_mock_generic_dialect()` helper with proper PropertyMock returning False for `has_fast_row_counts`
- **Files modified:** tests/integration/test_discovery.py
- **Commit:** 281c373

---

**Total deviations:** 2 auto-fixed (both test infrastructure updates caused by the new get_dialect call in _get_metadata_service)
**Impact on plan:** Minimal -- expected consequence of changing the metadata service factory function.

## Issues Encountered
None

## User Setup Required
None

## Next Phase Readiness
- Catalog-aware metadata fully operational for Databricks connections
- DESCRIBE EXTENDED properties available in get_table_schema responses
- Index gating working for all dialects via supports_indexes capability flag
- Plan 03 (if any) can build on this foundation for additional Databricks features

## Self-Check: PASSED

---
*Phase: 11-databricksdialect*
*Completed: 2026-04-15*
