# Codebase Concerns

**Analysis Date:** 2026-03-03

## Tech Debt

**Metrics module not integrated into MCP tools:**
- Issue: `src/metrics.py` implements full performance metrics tracking (PerformanceMetrics singleton) but is never instantiated or used in the active MCP tools
- Files: `src/metrics.py`, `src/mcp_server/schema_tools.py`, `src/mcp_server/query_tools.py`, `src/mcp_server/analysis_tools.py`
- Impact: NFR-001/NFR-002 performance requirements cannot be validated; metrics infrastructure is dead code (0% test coverage despite 258 lines)
- Fix approach: Integrate PerformanceMetrics.track() into all MCP tool entry points (schema_tools, query_tools, analysis_tools) to measure p50/p95/p99 latencies against thresholds defined in `src/db/metadata.py` (NFR_001_THRESHOLD_MS = 30000ms)

**Type ignores bypassing static analysis:**
- Issue: Three `# type: ignore` suppressions in query result processing without proper typing
- Files: `src/db/query.py` lines 546-548
- Impact: Runtime attributes set on Query dataclass bypass type checking; modifications to Query.\_columns, Query.\_rows, Query.\_total_rows_available are hidden from static analysis
- Fix approach: Either use TypedDict for query results or extend Query dataclass with optional fields instead of setting hidden attributes

**Percentile calculation correctness:**
- Issue: p95/p99 percentile indexing uses `int(len() * 0.95)` which truncates rather than properly rounding percentile position
- Files: `src/metrics.py` lines 67-68, 76-77
- Impact: Edge cases with small sample sizes (< 20 samples) may report incorrect percentiles
- Fix approach: Use proper percentile calculation or library (e.g., statistics.quantiles from Python 3.8+)

**Overly broad exception handling:**
- Issue: 25 instances of `except Exception:` blocks across the codebase mask specific failures
- Files: `src/db/metadata.py` (10 instances), `src/metrics.py` (1 instance), `src/mcp_server/*.py` (multiple instances)
- Impact: Difficult to debug failures; generic "Table not found" or "Access denied" may hide actual database errors, permission issues, or connection problems
- Fix approach: Replace broad Exception catches with specific exception types (e.g., `except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError)` for DB failures; `except (KeyError, AttributeError)` for lookup failures)

## Known Bugs

**Resource warnings in SQLite test fixtures:**
- Symptoms: 20+ ResourceWarning for "unclosed database" during test runs on metadata and query tests
- Files: Tests inherit from `tests/conftest.py` which provides mock_engine fixture; warnings from SQLAlchemy cursor close failures
- Trigger: Run `uv run pytest tests/ --cov` - warnings appear in test_metadata.py, test_query.py, test_pk_discovery.py
- Workaround: Warnings do not fail tests (pytest shows 367 passed) but indicate mock connection contexts not properly cleaning up
- Root cause: Mock engine's `__enter__/__exit__` don't properly call underlying SQLAlchemy connection cleanup

**Linting check passes but inconsistency remains:**
- Symptoms: `uv run ruff check src/` reports "All checks passed!" but one pre-existing warning noted in project memory
- Files: `src/metrics.py` line 24 (Generator import from typing instead of collections.abc - already corrected in visible code)
- Impact: Minimal - code follows PEP 585 conventions; no functional issues

## Security Considerations

**Query validation relies on sqlglot parsing resilience:**
- Risk: SQL parsing failures treated as "unsafe" may be exploited by crafting malformed SQL that bypasses validation
- Files: `src/db/validation.py` lines 93-99, `src/db/query.py` lines 336-341
- Current mitigation: ParseError exceptions return ValidationResult(is_safe=False) with PARSE_FAILURE reason; malformed queries are blocked
- Recommendations: Add telemetry for parse failures to detect attack patterns; log unparseable SQL signatures for analysis; consider SQL standardization/normalization before parsing

**Identifier sanitization assumes valid column names:**
- Risk: `_sanitize_identifier()` in `src/db/query.py` line 244 performs basic validation but may accept identifiers containing SQL syntax characters if SQL Server allows them
- Files: `src/db/query.py` line 85-86 (called during column selection)
- Current mitigation: Checks against regex pattern; blocklist approach for dangerous characters
- Recommendations: Use parameterized queries instead of identifier sanitization where possible; validate against sys.columns metadata before building query

**DML blocking prevents write operations but doesn't prevent information leakage:**
- Risk: SELECT queries can still infer schema structure and data patterns through error messages, execution time variations, or result set structure
- Files: `src/db/query.py` (execute_query blocks writes), `src/db/validation.py` (DENIED_TYPES enforcement)
- Current mitigation: execute_query hard-codes allow_write=False; 22 safe stored procedures whitelisted in SAFE_PROCEDURES
- Recommendations: Consider adding timing-attack protection (consistent execution time); rate-limit failed queries; log suspicious query patterns

## Performance Bottlenecks

**Foreign key candidate search may timeout on large databases:**
- Problem: FKCandidateSearch exhaustively queries value overlap via SQL INTERSECT for every candidate without early termination
- Files: `src/analysis/fk_candidates.py` lines 31-449 (449 lines total)
- Cause: No limits on result set size until final apply_result_limit(); INTERSECT queries read entire columns for cardinality comparison
- Improvement path: Add early exit for deterministic matches; implement sampling for large tables (> 100k rows); cache candidate metadata to avoid redundant INTERSECT queries

**Metadata service performs redundant queries for large schemas:**
- Problem: list_tables() queries metadata, then for each table calls get_row_count(), get_columns(), get_indexes(), get_foreign_keys() separately
- Files: `src/db/metadata.py` lines 60-260 (listing and detail methods)
- Cause: Sequential single-table queries instead of bulk collection; N+1 query pattern
- Improvement path: Batch column/index/FK queries per schema; use SQL Server DMVs for bulk metadata collection; cache results with TTL

**Column stats collection re-reads statistics for every query:**
- Problem: ColumnStatsCollector performs expensive statistical queries (min/max/mean/stddev/distinct counts) on each get_column_info() call without caching
- Files: `src/analysis/column_stats.py` lines 1-469
- Cause: Per-column aggregation queries; sample data collection for string value frequency analysis
- Improvement path: Implement result caching with configurable TTL; batch column stats queries; sample large columns (> 10M rows) instead of full scan

## Fragile Areas

**Query result formatting assumes all types are JSON-serializable:**
- Files: `src/db/query.py` lines 600-750 (result formatting); `src/mcp_server/query_tools.py` lines 97-107 (JSON response)
- Why fragile: Custom Python types (Decimal, datetime, UUID, bytes) require explicit formatting; if a new SQL column type is added, JSON serialization fails silently or errors
- Safe modification: Add explicit type handler registry; test with all SQL Server types (date/time/spatial/JSON/XML); use structured result objects with __json__ methods instead of dict
- Test coverage: Unit tests mock data types; integration tests need real SQL Server types (geography, geometry, hierarchyid, xml)

**Connection pooling configuration is global and immutable:**
- Files: `src/db/connection.py` lines 26-41 (PoolConfig), 66-74 (singleton initialization)
- Why fragile: PoolConfig set once at ConnectionManager creation; different databases may need different pool sizes (e.g., high-latency Azure SQL needs larger pool)
- Safe modification: Make pool config per-connection; validate pool settings against database type
- Test coverage: Tests use mock engines; real pool behavior untested with actual SQL Server

**Stored procedure allowlist is hardcoded and incomplete:**
- Files: `src/db/validation.py` lines 41-67 (SAFE_PROCEDURES frozenset with 22 procedures)
- Why fragile: New SQL Server versions add new safe SPs; custom DBs may have user-defined safe procedures; no way to extend allowlist without code changes
- Safe modification: Load allowlist from configuration file; support database-specific allowlists; document how to audit/extend allowlist
- Test coverage: Unit tests verify 22 known procedures; no tests for custom/third-party procedures

## Scaling Limits

**Memory usage unbounded for large result sets:**
- Current capacity: Query row limit 10,000 rows; sample_size limit 1,000 rows
- Limit: For wide tables (100+ columns with large strings), 10k rows * 1KB per value = 10MB+ in memory before JSON serialization
- Scaling path: Implement streaming/pagination results; use generators instead of collecting all rows; support offset-based continuation tokens

**Metadata service blocks on large schema introspection:**
- Current capacity: Tested threshold NFR-001 = 30 seconds for ~1000 tables
- Limit: DMV queries block connection while collecting all table/index/column metadata; no pagination or partial results
- Scaling path: Implement lazy loading per table; return schema summary first, then allow per-table drilldown; cache metadata with background refresh

**Analysis tools perform expensive searches linearly:**
- Current capacity: FKCandidateSearch checks each candidate table sequentially; no parallelization
- Limit: For databases with 100+ tables, single-threaded search may take minutes
- Scaling path: Implement parallel candidate evaluation; add progress/cancellation support; return partial results for long-running searches

## Dependencies at Risk

**sqlglot parsing reliability on future SQL dialects:**
- Risk: sqlglot may change query parsing behavior; malformed SQL handling could shift; new SQL Server syntax may break assumptions
- Impact: Validation bypass if parser changes behavior on edge cases
- Migration plan: Pin sqlglot to specific minor version; maintain test fixtures for known edge cases; monitor sqlglot changelog for breaking changes

**SQLAlchemy connection pooling behavior with SQL Server:**
- Risk: Connection reuse assumptions may not hold with Azure AD authentication token expiration
- Impact: Stale tokens cause "invalid token" errors mid-request
- Migration plan: Implement token refresh before pool connection checkout; add connection health check with pre_ping or custom validator

## Missing Critical Features

**No query result caching or result set versioning:**
- Problem: Large queries re-execute on every request; no deduplication of identical queries
- Blocks: Building datasets that depend on consistent snapshots of query results; LLM agents can't reason over historical query trends

**No audit logging of query execution:**
- Problem: Cannot trace which connections executed which queries or when
- Blocks: Compliance requirements (HIPAA, SOX, PCI-DSS) for query audit trails; debugging unauthorized access attempts

**No support for parameterized queries from MCP clients:**
- Problem: All queries go through validation and must be static SQL strings
- Blocks: Implementing safe filtering where client provides filter values at runtime

## Test Coverage Gaps

**MCP server entry point (server.py) - 88% coverage:**
- What's not tested: main() function and actual stdio transport initialization
- Files: `src/mcp_server/server.py` lines 60-61
- Risk: Startup failures or logging misconfiguration not caught by tests
- Priority: Low (critical path tested via tool tests)

**Metadata service - 67% coverage:**
- What's not tested: SQLite schema introspection fallback paths (lines 89-120, 145-147); row count queries for edge cases (lines 362-374)
- Files: `src/db/metadata.py` lines 75, 83, 89-120, 137, 149, 206, 220, 229-231, 262, 290-291, 337-342, 364, 372-374, 389-508, 534, 555-556, 579-592, 608-610, 622-626, 670-713
- Risk: SQLite schema queries may return unexpected results; databases without row count access fail silently
- Priority: High (affects schema exploration on non-SQL Server databases)

**Query service - 88% coverage:**
- What's not tested: Top query building for edge cases; text truncation boundary conditions; error recovery paths
- Files: `src/db/query.py` lines 105, 130-132, 185, 210, 244, 337-338, 341, 357, 389, 434, 474-481, 612-619, 679, 685-687, 732-750, 736-737, 745-746
- Risk: Large text truncation at 1000-char boundary may fail; malformed TSQL queries may not parse
- Priority: Medium (data truncation has user-visible impact)

**Metrics module - 0% coverage:**
- What's not tested: Entire PerformanceMetrics class; percentile calculations; thread safety
- Files: `src/metrics.py` (all 113 statements uncovered)
- Risk: Metrics calculations return incorrect results; concurrency issues under load
- Priority: High (NFR compliance feature completely untested)

**MCP tools - mixed coverage (16-88%):**
- What's not tested: analysis_tools.py at 16% (get_column_info, find_fk_candidates, find_pk_candidates mostly uncovered); schema_tools.py at 53%; query_tools.py at 75%
- Files: `src/mcp_server/analysis_tools.py` lines 93-145, 204-249, 332-418; `src/mcp_server/schema_tools.py` lines 27, 30, 33, 43-62, 117-174, 233-235, 340-344, 417-439
- Risk: MCP tool error handling paths untested; integration with ConnectionManager may fail; schema connection establishment edge cases
- Priority: Critical (these are the user-facing APIs)

**Validation edge cases - 80% coverage:**
- What's not tested: Complex parse failures; recursive control flow obfuscation patterns
- Files: `src/db/validation.py` lines 102, 110, 124, 178, 205-207, 223, 230-245
- Risk: Adversarial queries designed to exploit parser may slip through
- Priority: High (security-critical module)

---

*Concerns audit: 2026-03-03*
