# Codebase Concerns

**Analysis Date:** 2026-03-11

## Critical Issues

None identified. All previously identified critical issues have been addressed.

## Technical Debt

### Stored procedure allowlist extension requires TOML configuration

- **Category**: Code Quality
- **Location**: `src/db/validation.py` lines 41-82, `src/config.py` lines 1-288
- **Description**: The hardcoded 22-procedure allowlist (SAFE_PROCEDURES) can now be extended via TOML config, but there is no documentation or examples showing users how to audit and add custom safe procedures to their configuration file
- **Risk**: Users with custom safe stored procedures must manually discover the config option; no guidance on which procedures are safe to add
- **Effort**: Small (documentation and example TOML file)

### Connection pooling configuration is global per ConnectionManager

- **Category**: Architecture
- **Location**: `src/db/connection.py` lines 27-51 (PoolConfig dataclass), lines 66-537 (ConnectionManager singleton)
- **Description**: PoolConfig is set once during ConnectionManager initialization and applies to all connections. Different databases may benefit from different pool sizes (e.g., high-latency Azure SQL needs larger pool than local SQL Server)
- **Risk**: Suboptimal connection pool tuning for mixed database scenarios; one-size-fits-all approach may cause connection exhaustion or wasted connections
- **Effort**: Medium (add per-connection pool config overrides)

### Query result JSON serialization assumes all types are handled

- **Category**: Code Quality
- **Location**: `src/type_registry.py` lines 1-58 (type registry), `src/db/query.py` lines 680-773 (result formatting), `src/mcp_server/query_tools.py` lines 97-107 (JSON response)
- **Description**: TypeRegistry handles known SQL Server types (datetime, Decimal, bytes, UUID) but has no fallback for unknown types. If SQL Server introduces new types or custom types are used, serialization will fail with TypeError
- **Risk**: Runtime failures on custom types (geography, geometry, hierarchyid, XML) or future SQL Server types; error message unhelpful ("Object of type X is not JSON serializable")
- **Effort**: Small (add catch-all handler that converts unknown types to string representation with type annotation)

## Known Bugs

### ResourceWarning for unclosed SQLite database in tests

- **Symptoms**: 44 ResourceWarnings during test runs: "unclosed database in <sqlite3.Connection object at 0x...>"
- **Location**: Tests using mock SQLAlchemy engines in `tests/conftest.py`, appearing in `tests/unit/test_metadata.py`, `tests/unit/test_query.py`, `tests/unit/test_pk_discovery.py`
- **Trigger**: Run `uv run pytest tests/ -W default::ResourceWarning` - warnings appear in metadata and query tests
- **Workaround**: Warnings do not fail tests (682 collected, 634 passed, 41 skipped, 7 failed) and do not affect production code (only SQLite mocks, not real SQL Server connections)
- **Root Cause**: Mock SQLAlchemy engines created in test fixtures do not properly call `connection.close()` in teardown; pytest's fixture cleanup may not reach SQLAlchemy's connection pool disposal

### Azure AD authentication integration tests fail on expired token

- **Symptoms**: 7 test failures in `tests/integration/test_azure_ad_auth.py` with "ClientAuthenticationError: DefaultAzureCredential failed to retrieve a token"
- **Location**: `tests/integration/test_azure_ad_auth.py` (all tests), `src/db/azure_auth.py` line 57 (get_token)
- **Trigger**: Run `uv run pytest tests/integration/test_azure_ad_auth.py` when Azure CLI token has expired (TokensValidFrom date is newer than grant issued date)
- **Workaround**: Run `az logout && az login --tenant <tenant-id>` before tests
- **Root Cause**: Tests use DefaultAzureCredential which relies on cached Azure CLI tokens; cached tokens expire and are not automatically refreshed; test does not mock Azure credential acquisition

## Security Considerations

### Query validation relies on sqlglot parsing resilience

- **Risk**: SQL parsing failures are treated as "unsafe" and blocked, but adversaries may craft malformed SQL that bypasses validation if sqlglot parser evolves or has edge-case bugs
- **Location**: `src/db/validation.py` lines 106-112 (parse error handling), `src/db/query.py` lines 336-341 (validation integration)
- **Current Mitigation**: ParseError exceptions return `ValidationResult(is_safe=False)` with PARSE_FAILURE reason; malformed queries are blocked by default-deny
- **Recommendations**: Add telemetry for parse failures to detect attack patterns; log unparseable SQL signatures for security analysis; consider SQL standardization/normalization before parsing; pin sqlglot to specific minor version and monitor changelog for breaking changes

### Identifier sanitization validates but does not guarantee SQL injection protection

- **Risk**: `_validate_identifier()` in `src/db/query.py` performs regex validation and checks for dangerous characters, but may accept edge-case identifiers that SQL Server allows containing SQL syntax
- **Location**: `src/db/query.py` lines 85-95 (identifier validation), line 244 (sanitization call sites)
- **Current Mitigation**: Allowlist regex pattern `^[a-zA-Z_][a-zA-Z0-9_]*$`; blocklist for quotes, semicolons, comments, whitespace; validation before query building
- **Recommendations**: Use parameterized queries instead of identifier sanitization where possible; validate identifiers against actual sys.columns metadata before building queries; add integration tests with adversarial identifier patterns

### SELECT queries can infer schema structure through timing and error messages

- **Risk**: Even with DML blocked, attackers can use SELECT queries to infer schema structure, data patterns, and relationships through execution time variations, result set structure, and error messages
- **Location**: `src/db/query.py` (execute_query blocks writes but allows reads), `src/db/validation.py` (DENIED_TYPES enforcement)
- **Current Mitigation**: execute_query hard-codes `allow_write=False`; 22 safe stored procedures allowlisted in SAFE_PROCEDURES + config-driven extensions; query validation blocks DML/DDL/DCL
- **Recommendations**: Consider adding timing-attack protection (constant execution time padding); rate-limit failed queries per connection; log suspicious query patterns (e.g., systematic table enumeration); add connection-level query budget/throttling

## Performance Bottlenecks

### Foreign key candidate search may timeout on large databases

- **Problem**: FKCandidateSearch exhaustively queries value overlap via SQL INTERSECT for every candidate pair without early termination or sampling
- **Location**: `src/analysis/fk_candidates.py` (449 lines total)
- **Cause**: No limits on result set size until final `apply_result_limit()`; INTERSECT queries read entire columns for cardinality comparison; no caching of candidate metadata across searches
- **Improvement Path**: Add early exit for deterministic matches (100% overlap with matching cardinality); implement sampling for large tables (> 100k rows); cache candidate metadata to avoid redundant INTERSECT queries; add search timeout with partial results

### Metadata service performs N+1 queries for schema listings

- **Problem**: `list_tables()` queries basic metadata, then for each table calls `get_row_count()`, `get_columns()`, `get_indexes()`, `get_foreign_keys()` separately
- **Location**: `src/db/metadata.py` lines 60-714 (listing and detail methods)
- **Cause**: Sequential single-table queries instead of bulk collection; N+1 query pattern for large schemas
- **Improvement Path**: Batch column/index/FK queries per schema using SQL Server DMVs (sys.columns, sys.indexes, sys.foreign_keys); implement caching layer with configurable TTL; return summary metadata first with lazy loading for details

### Column statistics collection re-queries for every call

- **Problem**: ColumnStatsCollector performs expensive statistical queries (MIN/MAX/AVG/STDEV/COUNT DISTINCT) on each `get_column_info()` call without caching
- **Location**: `src/analysis/column_stats.py` (469 lines total)
- **Cause**: Per-column aggregation queries; sample data collection for string value frequency analysis; no result caching
- **Improvement Path**: Implement result caching with configurable TTL; batch column stats queries across multiple columns; sample large columns (> 10M rows) instead of full scan; use SQL Server column statistics metadata when available

## Fragile Areas

### NFR-001 threshold logging may produce false positives on slow databases

- **Location**: `src/db/metadata.py` lines 80-84 (list_schemas), similar patterns throughout metadata service
- **Why Fragile**: NFR-001 threshold is hardcoded to 30,000ms and logged as warnings when exceeded, but threshold does not account for database load, network latency, or Azure SQL throttling
- **Safe Modification**: Make NFR-001 threshold configurable per-connection or per-database type; add context to warnings (e.g., "exceeded threshold by 5%, may be transient"); separate performance regression detection from absolute threshold enforcement
- **Test Coverage**: Performance tests in `tests/performance/test_nfr001.py` validate threshold enforcement but do not test threshold configuration or warning context

### MCP tool exception handlers catch Exception as last-resort fallback

- **Location**: `src/mcp_server/schema_tools.py` lines 259-269, `src/mcp_server/analysis_tools.py` lines 138-144, `src/mcp_server/query_tools.py` lines 119-121, `src/config.py` lines 257-259
- **Why Fragile**: Eight `except Exception:` blocks serve as last-resort error handlers after specific exception types (ValueError, ConnectionError, SQLAlchemyError). They classify SQLAlchemyError with `_classify_db_error()` but treat all other exceptions as "Unexpected error"
- **Safe Modification**: These are appropriate as final safety nets; changes should add specific exception types before the Exception handler (e.g., add KeyError, AttributeError handlers) rather than removing the catch-all
- **Test Coverage**: MCP tools have 74-90% coverage but exception path testing is incomplete; error classification is tested via `_classify_db_error()` unit tests but not integration-tested through MCP tool layer

### Test fixtures use SQLite mocks but production uses SQL Server

- **Location**: `tests/conftest.py` (mock engine fixtures), tests throughout `tests/unit/` directory
- **Why Fragile**: SQLite has different type handling, identifier quoting, and metadata schema than SQL Server; tests may pass on SQLite mocks but fail on real SQL Server (or vice versa)
- **Safe Modification**: Expand integration test coverage in `tests/integration/` with real SQL Server database; add SQL Server-specific type tests (datetime2, uniqueidentifier, geography); validate metadata queries against SQL Server DMVs
- **Test Coverage**: 51 test files, 682 tests total, 88% overall coverage; integration tests exist but are partially skipped (41 skipped tests, likely due to missing test database connection)

## Scaling Limits

### Memory usage unbounded for large result sets

- **Current Capacity**: Query row limit 10,000 rows (default 1,000, max 10,000 configurable via TOML); sample_size limit 1,000 rows (default 5, max 1,000)
- **Limit**: For wide tables (100+ columns with large VARCHAR values), 10k rows * 1KB per value = 10MB+ in memory before JSON serialization; no pagination or streaming
- **Scaling Path**: Implement streaming/pagination results with continuation tokens; use generators instead of collecting all rows in memory; support OFFSET/FETCH NEXT for pagination; add query result caching with size limits

### Metadata service blocks on large schema introspection

- **Current Capacity**: NFR-001 threshold = 30,000ms (30 seconds) for operations with ~1000 tables
- **Limit**: DMV queries block connection while collecting all table/index/column metadata; no pagination or partial results; single-threaded sequential processing
- **Scaling Path**: Implement lazy loading per table with summary metadata first; allow per-table drilldown on demand; cache metadata with background refresh; add pagination to list_tables/list_schemas

### Analysis tools perform expensive searches linearly

- **Current Capacity**: FKCandidateSearch checks each candidate table sequentially; no parallelization or progress reporting
- **Limit**: For databases with 100+ tables, single-threaded search may take minutes; no cancellation mechanism; client must wait for full search to complete
- **Scaling Path**: Implement parallel candidate evaluation using asyncio or ThreadPoolExecutor; add progress/cancellation support via MCP protocol; return partial results for long-running searches; cache FK candidate metadata between searches

## Dependencies at Risk

### sqlglot parsing reliability on future SQL dialects

- **Risk**: sqlglot may change query parsing behavior in minor versions; new SQL Server syntax (e.g., T-SQL 2025 features) may break parsing assumptions; malformed SQL handling could shift
- **Impact**: Validation bypass if parser changes behavior on edge cases; queries previously blocked may pass (or vice versa); parse errors may expose internal validation logic
- **Migration Plan**: Pin sqlglot to specific minor version in `pyproject.toml`; maintain test fixtures for known edge cases and adversarial queries; monitor sqlglot changelog for breaking changes before upgrading; add regression tests for T-SQL dialect quirks

### SQLAlchemy connection pooling with Azure AD token expiration

- **Risk**: Connection reuse assumptions may not hold with Azure AD authentication token expiration (~3600s); stale tokens in pool cause "invalid token" errors mid-request
- **Impact**: Connections fail with authentication errors after token expiry despite successful initial connection; requires manual disconnect/reconnect cycle
- **Current Mitigation**: `azure_ad_pool_recycle=2700` (45 minutes) recycles connections before 1-hour token expiry; `pool_pre_ping=True` validates connections before use
- **Migration Plan**: Implement token refresh hook before pool connection checkout; add connection health check with custom validator that tests auth token validity; handle token refresh failures with automatic disconnect and reconnect

## Missing Critical Features

### No query result caching or result set versioning

- **Problem**: Large queries re-execute on every request with no deduplication of identical queries; no way to reference previous query results by ID
- **Blocks**: Building datasets that depend on consistent snapshots of query results; LLM agents cannot reason over historical query trends or compare results across time; expensive analytics queries repeat unnecessarily
- **Suggested Addition**: Implement query result cache with TTL and size limits; add `query_id`-based result retrieval; support result versioning with snapshot timestamps

### No audit logging of query execution

- **Problem**: Cannot trace which connections executed which queries, when, or by whom; no persistent log of query history
- **Blocks**: Compliance requirements (HIPAA, SOX, PCI-DSS) for query audit trails; debugging unauthorized access attempts; forensic analysis after security incidents
- **Suggested Addition**: Add structured query audit log with connection ID, query text (sanitized), execution time, result count, and error status; support pluggable audit backends (file, database, cloud logging)

### No support for parameterized queries from MCP clients

- **Problem**: All queries go through validation as static SQL strings; clients cannot provide filter values at runtime without string interpolation
- **Blocks**: Implementing safe dynamic filtering where client provides values (e.g., "get users WHERE age > ?"); forces clients to build SQL strings with values embedded, increasing injection risk
- **Suggested Addition**: Add MCP tool parameter for query parameters; extend execute_query to accept `params: dict[str, Any]`; use SQLAlchemy's bindparams for safe parameter substitution

## Test Coverage Gaps

### MCP server entry point - 100% coverage ✓

- **Status**: Fully covered (up from 88%)
- **Location**: `src/mcp_server/server.py` lines 1-23
- **Risk**: None (startup and transport initialization now tested)

### Metadata service - 74% coverage

- **What's Not Tested**: SQLite schema introspection fallback paths; row count queries for edge cases (empty tables, missing permissions); error recovery in foreign key collection
- **Location**: `src/db/metadata.py` (57 uncovered statements, 13 partial branches out of 242 statements)
- **Risk**: SQLite schema queries may return unexpected results; databases without row count access fail silently; FK metadata collection errors masked by broad exception handlers
- **Priority**: High (affects schema exploration on non-SQL Server databases and production error scenarios)

### Query service - 88% coverage

- **What's Not Tested**: COUNT(*) query building edge cases; text truncation boundary conditions with config-driven limits; error recovery paths in result formatting
- **Location**: `src/db/query.py` (29 uncovered statements, 16 partial branches out of 270 statements)
- **Risk**: Large text truncation at configurable boundary may fail on edge cases; malformed T-SQL queries may not parse correctly; total_rows_available calculation may fail silently
- **Priority**: Medium (data truncation and pagination have user-visible impact)

### Validation edge cases - 80% coverage

- **What's Not Tested**: Complex parse failures; recursive control flow obfuscation patterns; CTE-wrapped write detection in deeply nested queries
- **Location**: `src/db/validation.py` (16 uncovered statements, 6 partial branches out of 89 statements)
- **Risk**: Adversarial queries designed to exploit parser may slip through; deeply nested CTEs with writes may not be detected
- **Priority**: High (security-critical module must handle all edge cases)

### MCP tools - 74-90% coverage

- **What's Not Tested**: schema_tools.py at 74% (connect_database edge cases, error classification paths); analysis_tools.py at 88% (FK/PK candidate discovery error handling); query_tools.py at 90% (execute_query validation errors)
- **Location**: `src/mcp_server/schema_tools.py` (37 uncovered statements out of 178), `src/mcp_server/analysis_tools.py` (6 uncovered out of 87), `src/mcp_server/query_tools.py` (5 uncovered out of 67)
- **Risk**: MCP tool error handling paths untested; integration with ConnectionManager may fail on edge cases (e.g., connection pool exhaustion, timeout); error message formatting may break on unexpected exceptions
- **Priority**: Critical (these are the user-facing APIs; all error paths should be tested)

### Config loading - 93% coverage

- **What's Not Tested**: TOML parse error handling; environment variable substitution edge cases; invalid SP name validation
- **Location**: `src/config.py` (7 uncovered statements out of 106)
- **Risk**: Malformed TOML files may crash server startup; environment variable references with missing variables may fail silently
- **Priority**: Medium (config loading failures are startup-time issues, easier to debug than runtime failures)

## Resolved Concerns

The following concerns from the 2026-03-03 audit have been **fully resolved** via v1.1 milestone work:

### ✓ Metrics module not integrated (RESOLVED)

- **Resolution**: `src/metrics.py` deleted in commit 1fda3e7 (2026-03-09); module was dead code with 0% coverage
- **Impact**: NFR-001/NFR-002 performance tracking now uses direct logging in metadata service (`src/db/metadata.py` lines 80-84) instead of separate metrics singleton

### ✓ Type ignores bypassing static analysis (RESOLVED)

- **Resolution**: Three `# type: ignore` suppressions removed in commit 994acb3 (2026-03-09); Query dataclass now has proper fields (`columns`, `rows`, `total_rows_available`) instead of monkey-patched attributes
- **Impact**: Static type checking now covers Query result handling; no hidden attribute assignments

### ✓ Overly broad exception handling (RESOLVED)

- **Resolution**: All 25 `except Exception:` instances replaced with specific exception types in v1.1 work; now only 8 last-resort Exception handlers remain in MCP tools, all with proper SQLAlchemyError classification via `_classify_db_error()`
- **Impact**: Specific database errors (OperationalError, DatabaseError) now properly surfaced; validation errors (ValueError) handled separately; only truly unexpected errors caught by Exception handler

### ✓ Linting check inconsistency (RESOLVED)

- **Resolution**: Pre-existing Generator import warning cleared; `uv run ruff check src/` now reports "All checks passed!"
- **Impact**: Zero linting warnings; codebase follows PEP 585 conventions

### ✓ Stored procedure allowlist is hardcoded (RESOLVED)

- **Resolution**: Allowlist now extensible via TOML config (`allowed_stored_procedures` in `src/config.py`); `get_allowed_procedures()` merges hardcoded 22 safe procedures with config-provided additions
- **Impact**: Users can add custom safe procedures without code changes; remaining concern is lack of documentation (moved to Technical Debt)

---

*Generated by gsd-codebase-mapper | Focus: concerns*
*Date: 2026-03-11*
