# Requirements: dbmcp v1.1

**Defined:** 2026-03-06
**Core Value:** LLM agents can explore and query SQL Server databases safely, with validated read-only access and clear error reporting.

## v1.1 Requirements

Requirements for concern handling milestone. Each maps to roadmap phases.

### Code Quality

- [x] **QUAL-01**: Dead metrics module (`src/metrics.py`) removed from codebase with no remaining references
- [x] **QUAL-02**: All 25 broad `except Exception:` blocks replaced with specific exception types (SQLAlchemy, pyodbc, stdlib) while preserving user-facing error messages
- [x] **QUAL-03**: Three `# type: ignore` suppressions in `src/db/query.py` eliminated by proper typing (QueryResult wrapper or extended dataclass fields)

### Test Coverage

- [x] **TEST-01**: All source modules at 70% or higher test coverage (analysis_tools currently 16%, schema_tools 53%, metadata 67%)
- [x] **TEST-02**: Coverage reporting configured and baseline established for CI enforcement

### Connection Management

- [x] **CONN-01**: Azure AD token refresh handled via `pool_recycle` (< token lifetime) and `pool_pre_ping` so pooled connections with expired tokens are discarded before use
- [x] **CONN-02**: Database connections cleaned up when MCP session ends via `atexit` handler (or FastMCP lifecycle hook if available)

### Security Hardening

- [x] **SEC-01**: Identifier sanitization validates column names against `sys.columns` metadata before incorporating into SQL, replacing regex blocklist approach
- [x] **SEC-02**: sqlglot pinned to `>=29.0.0,<30.0.0` in pyproject.toml with edge case test fixtures covering malformed SQL, injection attempts, T-SQL syntax, and comment obfuscation

### Infrastructure

- [x] **INFRA-01**: Type handler registry unifies `_truncate_value()` and `_pre_serialize()` into single conversion pipeline with fallback logging for unknown types
- [x] **INFRA-02**: Optional TOML config file (`~/.dbmcp/config.toml` or `dbmcp.toml`) supporting named connections, default parameters, and SP allowlist extensions

## Future Requirements

### Performance

- **PERF-01**: Query result caching with TTL for identical queries
- **PERF-02**: Streaming/pagination for large result sets
- **PERF-03**: Parallel FK candidate evaluation

### Compliance

- **COMP-01**: Audit logging of query execution
- **COMP-02**: Parameterized queries from MCP clients

## Out of Scope

| Feature | Reason |
|---------|--------|
| Resource warning fix in test fixtures | Cosmetic; warnings don't affect test outcomes |
| Metadata service N+1 query optimization | Performance concern, not a correctness issue |
| Column stats caching | Performance optimization, not a concern fix |
| Real-time chat/streaming MCP | Different protocol requirement |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUAL-01 | Phase 3 | Complete |
| QUAL-02 | Phase 3 | Complete |
| QUAL-03 | Phase 3 | Complete |
| TEST-01 | Phase 3 | Complete |
| TEST-02 | Phase 3 | Complete |
| CONN-01 | Phase 4 | Complete |
| CONN-02 | Phase 4 | Complete |
| SEC-01 | Phase 5 | Complete |
| SEC-02 | Phase 5 | Complete |
| INFRA-01 | Phase 6 | Complete |
| INFRA-02 | Phase 6 | Complete |

**Coverage:**
- v1.1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0

---
*Requirements defined: 2026-03-06*
*Last updated: 2026-03-06 after initial definition*
