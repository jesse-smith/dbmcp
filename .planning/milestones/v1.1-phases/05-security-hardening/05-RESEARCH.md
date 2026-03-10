# Phase 5: Security Hardening - Research

**Researched:** 2026-03-09
**Domain:** SQL injection prevention via metadata-based identifier validation + sqlglot edge case coverage
**Confidence:** HIGH

## Summary

Phase 5 replaces the regex-based `_sanitize_identifier()` in QueryService with metadata-based validation, where user-supplied identifiers (column names, table names, schema names) are checked against actual database objects before being embedded in SQL. The main attack surface is `get_sample_data`, which is the only MCP tool that accepts a user-supplied `columns` parameter and embeds those names directly in SQL via string formatting. Table/schema names across tools also need validation but are already partially protected (e.g., `get_table_schema` checks `table_exists()`, analysis tools use parameterized INFORMATION_SCHEMA queries).

The second deliverable is tightening the sqlglot pin from `>=26.0.0,<30.0.0` to `>=29.0.0,<30.0.0` and adding ~20-30 focused edge case test fixtures. The v29 floor is important because `exp.Execute` node handling changed between v26 and v29 (the codebase already depends on `exp.Execute` and `exp.ExecuteSql` which are v29 behaviors). The currently installed version is 29.0.1.

**Primary recommendation:** Add a `validate_identifier()` method to QueryService that uses MetadataService's cached column/table lists as the source of truth, with case-insensitive matching. Wire MetadataService into QueryService via constructor injection. Create a dedicated edge case test file for sqlglot validation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Validate all user-supplied identifiers: columns, table names, and schema names against actual database metadata
- Only user-supplied identifiers (from MCP tool parameters) require validation -- internally-sourced identifiers (e.g., column names returned from sys.columns by analysis tools) are trusted
- Primary focus is get_sample_data (only tool with user-supplied columns param) plus table/schema validation across tools
- Replace the current regex-based `_sanitize_identifier()` entirely with metadata lookup -- no regex as first pass, metadata is the single source of truth
- If metadata lookup fails (e.g., permission denied on sys.tables), fail open: fall back to the existing regex check and log a warning
- When an identifier fails metadata validation, reject the entire tool call with an error -- no partial execution
- Error message names the invalid identifier specifically: "Column 'foobar' does not exist in [dbo].[Users]" -- don't list valid alternatives
- Comparison is case-insensitive (matching SQL Server default collation behavior)
- Validation lives inside QueryService (centralized), not at the MCP tool layer
- Inject MetadataService into QueryService via constructor to provide metadata access
- Reuse MetadataService's existing cache (no fresh queries per validation)
- Tighten sqlglot pin from `>=26.0.0,<30.0.0` to `>=29.0.0,<30.0.0` in pyproject.toml
- Add a test that asserts `sqlglot.__version__` >= 29.0.0
- ~20-30 focused, practical test cases in a separate dedicated test file
- Fixtures test sqlglot query parsing only -- identifier validation gets its own tests elsewhere

### Claude's Discretion
- Service wiring approach: factory pattern vs direct MetadataService injection in each tool function
- Exact edge case selection for the ~20-30 fixture set (prioritize patterns most relevant to read-only SQL Server access)
- Test file organization for identifier validation tests (new file vs extending existing test_query.py)
- How to handle the MetadataService dependency in QueryService tests (mock vs test fixtures)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SEC-01 | Identifier sanitization validates column names against sys.columns metadata before incorporating into SQL, replacing regex blocklist approach | MetadataService already has `get_columns()` with caching; QueryService constructor needs MetadataService injection; `_sanitize_identifier()` replacement with metadata lookup + case-insensitive comparison |
| SEC-02 | sqlglot pinned to `>=29.0.0,<30.0.0` with edge case test fixtures covering malformed SQL, injection attempts, T-SQL syntax, and comment obfuscation | Current pin is `>=26.0.0,<30.0.0` on line 29 of pyproject.toml; installed version is 29.0.1; v29 Execute/ExecuteSql node handling confirmed working; existing test_validation.py has 142+ lines of patterns to follow |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlglot | >=29.0.0,<30.0.0 | SQL parsing + AST validation | Already used for query validation; v29 needed for Execute node handling |
| sqlalchemy | >=2.0.0 | DB connection + metadata introspection | Already used; inspector provides column/table metadata |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=7.0.0 | Test framework | Edge case fixtures with parametrize |

No new dependencies needed. This phase only tightens an existing pin and restructures existing code.

**Installation:**
```bash
# No new packages -- just pin tightening in pyproject.toml
# Change line 29: "sqlglot>=26.0.0,<30.0.0" -> "sqlglot>=29.0.0,<30.0.0"
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  db/
    query.py          # QueryService gains MetadataService dependency + validate_identifier()
    metadata.py       # MetadataService unchanged (already has get_columns, table_exists)
    validation.py     # validate_query() unchanged (edge case tests exercise it)
  mcp_server/
    query_tools.py    # get_sample_data wires MetadataService into QueryService
    schema_tools.py   # get_table_schema already validates; may wire MetadataService
tests/
  unit/
    test_validation.py           # Existing -- untouched
    test_validation_edge_cases.py  # NEW: ~20-30 sqlglot edge case fixtures
    test_identifier_validation.py  # NEW (or extend test_query.py): metadata-based validation tests
    test_query.py                # Existing -- QueryService constructor tests updated
```

### Pattern 1: Constructor Injection for MetadataService
**What:** Add optional `metadata_service: MetadataService | None = None` parameter to `QueryService.__init__()`
**When to use:** Always -- this is the locked decision
**Example:**
```python
# src/db/query.py
class QueryService:
    def __init__(self, engine: Engine, metadata_service: MetadataService | None = None):
        self.engine = engine
        self._metadata_service = metadata_service
```

### Pattern 2: Metadata-Based Identifier Validation with Fail-Open
**What:** Validate identifiers against MetadataService cache, fall back to regex on metadata failure
**When to use:** When any user-supplied identifier is about to be embedded in SQL
**Example:**
```python
def _validate_identifier(self, identifier: str, valid_names: list[str], context: str) -> str:
    """Validate and bracket-quote a user-supplied identifier.

    Args:
        identifier: User-supplied name (column, table, schema)
        valid_names: List of valid names from metadata
        context: Error context (e.g., "[dbo].[Users]")

    Returns:
        Bracket-quoted identifier (e.g., "[ColumnName]")

    Raises:
        ValueError: If identifier not found in valid_names
    """
    # Case-insensitive lookup
    name_map = {name.lower(): name for name in valid_names}
    canonical = identifier.lower()

    if canonical not in name_map:
        raise ValueError(f"Column '{identifier}' does not exist in {context}")

    # Use the actual casing from metadata for the bracket-quoted result
    actual_name = name_map[canonical]

    dialect_name = self.engine.dialect.name
    if dialect_name == "sqlite":
        return actual_name
    return f"[{actual_name}]"
```

### Pattern 3: Service Wiring in Tool Functions
**What:** Create MetadataService in tool function and pass to QueryService
**When to use:** In `get_sample_data` and any tool creating QueryService
**Example:**
```python
# src/mcp_server/query_tools.py
def _sync_work():
    conn_manager = get_connection_manager()
    engine = conn_manager.get_engine(connection_id)
    metadata_svc = MetadataService(engine)
    query_svc = QueryService(engine, metadata_service=metadata_svc)
    # ...
```

### Anti-Patterns to Avoid
- **Regex layering before metadata:** User explicitly decided metadata is the single source of truth. Don't add regex as "first pass."
- **Listing valid alternatives in error messages:** Decision says "don't list valid alternatives" -- just name the invalid identifier.
- **Validating internally-sourced identifiers:** Analysis tools (column_stats, pk_discovery, fk_candidates) use identifiers returned from INFORMATION_SCHEMA/sys.columns queries. These are trusted.
- **Breaking backward compatibility of QueryService constructor:** Make metadata_service optional (`None` default) so existing code/tests that create `QueryService(engine)` still work. When None, fall back to regex (the fail-open path).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Column existence checking | Custom sys.columns queries | `MetadataService.get_columns()` | Already cached, returns Column objects with `.column_name` |
| Table existence checking | Custom sys.tables queries | `MetadataService.table_exists()` | Already implemented |
| SQL parsing for injection detection | Custom regex patterns | `sqlglot.parse()` + `validate_query()` | AST-based; handles comments, nesting, obfuscation |
| Case-insensitive string matching | `.upper()` comparisons | `dict` with `.lower()` keys | Preserves original casing for bracket quoting |

**Key insight:** MetadataService already provides all the metadata needed. The main work is wiring it into QueryService and replacing the regex check with a lookup against cached results.

## Common Pitfalls

### Pitfall 1: SQLite Test Compatibility
**What goes wrong:** MetadataService uses SQLAlchemy inspector which works differently for SQLite (no schemas, no bracket quoting)
**Why it happens:** Most unit tests use SQLite mock engines
**How to avoid:** When `metadata_service is None` or `dialect_name == "sqlite"`, fall back to regex path. SQLite tests don't exercise the metadata validation path.
**Warning signs:** Tests that create `QueryService(mock_engine)` without MetadataService start failing

### Pitfall 2: MetadataService Cache Staleness
**What goes wrong:** Column added to table after MetadataService cached the column list; validation rejects the new column
**Why it happens:** MetadataService uses SQLAlchemy inspector which caches per-session
**How to avoid:** This is a known, accepted tradeoff per user decision. Don't add cache invalidation. Document the staleness risk.

### Pitfall 3: Metadata Access Failure Breaks Working Queries
**What goes wrong:** SQL Server permissions prevent querying sys.columns; all get_sample_data calls with column filters start failing
**Why it happens:** Not all SQL Server users have metadata visibility
**How to avoid:** Fail-open pattern: catch SQLAlchemyError from MetadataService, log warning, fall back to existing regex. This is a locked decision.
**Warning signs:** `MetadataService.get_columns()` returning empty list when table has columns

### Pitfall 4: Case-Sensitive Collation Mismatch
**What goes wrong:** Rare SQL Server databases use case-sensitive collation; metadata returns "UserName" but user passes "username" which matches via case-insensitive check but SQL Server rejects the query
**Why it happens:** We use case-insensitive matching (user decision) but SQL Server's collation may be case-sensitive
**How to avoid:** Use the actual casing from metadata (not the user's casing) when building SQL. The `name_map` pattern above handles this -- it returns the metadata's actual casing.

### Pitfall 5: Schema Name Validation Scope
**What goes wrong:** Attempting to validate schema names requires listing all schemas, which is a separate metadata call
**Why it happens:** MetadataService has `list_schemas()` but it's heavier than column lookups
**How to avoid:** For `get_sample_data`, the primary validation is columns. Table/schema validation is already handled by tools that call `table_exists()`. Don't over-engineer schema validation for the sample data path -- the table itself being missing is caught by SQL execution errors.

## Code Examples

### Current _sanitize_identifier (to be replaced)
```python
# src/db/query.py lines 231-254 -- CURRENT (regex-based)
def _sanitize_identifier(self, identifier: str) -> str:
    if not re.match(r'^[a-zA-Z0-9_\s]+$', identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    dialect_name = self.engine.dialect.name
    if dialect_name == "sqlite":
        return identifier
    else:
        return f"[{identifier}]"
```

### MetadataService.get_columns() -- existing, reusable
```python
# src/db/metadata.py lines 511-559
def get_columns(self, table_name: str, schema_name: str = "dbo") -> list[Column]:
    # Uses SQLAlchemy inspector -- cached per session
    # Returns Column objects with .column_name attribute
```

### Existing test_validation.py parametrize pattern (follow this)
```python
# tests/unit/test_validation.py -- parametrized denial tests
@pytest.mark.parametrize(
    "sql,category",
    [
        ("INSERT INTO users (name) VALUES ('x')", DenialCategory.DML),
        # ...
    ],
    ids=["insert", ...],
)
def test_denied_with_category(self, sql, category):
    result = validate_query(sql)
    assert result.is_safe is False
    assert result.reasons[0].category == category
```

### get_sample_data MCP tool wiring (current, needs MetadataService)
```python
# src/mcp_server/query_tools.py lines 80-83 -- CURRENT
def _sync_work():
    conn_manager = get_connection_manager()
    engine = conn_manager.get_engine(connection_id)
    query_svc = QueryService(engine)
    # NEEDS: metadata_svc = MetadataService(engine)
    # NEEDS: query_svc = QueryService(engine, metadata_service=metadata_svc)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sqlglot Command node for EXEC | sqlglot Execute/ExecuteSql nodes | sqlglot v29 | Codebase already handles both paths; floor bump codifies this |
| Regex identifier sanitization | Metadata-based validation | This phase | Eliminates bypass via regex-valid-but-malicious identifiers |

**Deprecated/outdated:**
- `_sanitize_identifier()` regex approach: Being replaced in this phase. Keep as fallback only for fail-open path.

## Surface Area Audit

Confirmed user-supplied identifier paths:

| Tool | User-Supplied Params | Current Protection | Action Needed |
|------|---------------------|-------------------|---------------|
| `get_sample_data` | `columns`, `table_name`, `schema_name` | `_sanitize_identifier()` regex for columns; bracket-quoting for table/schema | **Primary target** -- replace regex with metadata validation for columns |
| `get_table_schema` | `table_name`, `schema_name` | `table_exists()` check before proceeding | Already safe -- metadata validates table existence |
| `list_tables` | `schema_name`, `name_pattern` | Parameterized queries in MetadataService | Already safe -- uses SQLAlchemy parameters |
| `execute_query` | `query_text` | `validate_query()` AST denylist | Already safe -- sqlglot validates full query |
| `get_column_info` | `columns`, `table_name`, `schema_name` | `column_exists()` via parameterized INFORMATION_SCHEMA | Safe but embeds in bracket-quoted SQL after check |
| `find_pk_candidates` | `table_name`, `schema_name` | `table_exists()` via parameterized INFORMATION_SCHEMA | Already safe |
| `find_fk_candidates` | `table_name`, `column_name`, `schema_name` | Parameterized INFORMATION_SCHEMA checks | Already safe |

**Conclusion:** `get_sample_data` columns parameter is the only unprotected user-supplied identifier path. Table/schema names across tools are either already validated or passed through SQLAlchemy inspector (which parameterizes). The audit confirms the CONTEXT.md assessment.

## Edge Case Fixture Categories

Recommended ~25 test cases for the sqlglot edge case file, organized by attack pattern:

### Comment Injection (~4 tests)
- Single-line comment hiding: `SELECT * FROM users -- DROP TABLE users`
- Multi-line comment wrapping: `SELECT * FROM users /* ; DROP TABLE users */`
- Nested comments: `SELECT /* /* */ DROP TABLE users */ 1`
- Comment between keywords: `DR/**/OP TABLE users`

### Semicolon Batching (~4 tests)
- Simple batch: `SELECT 1; DROP TABLE users`
- Batch with whitespace: `SELECT 1 ;  DROP TABLE users`
- Batch with comment separation: `SELECT 1; -- safe\nDROP TABLE users`
- Triple batch: `SELECT 1; SELECT 2; DELETE FROM users`

### UNION Injection (~3 tests)
- Basic UNION attack: `SELECT name FROM users UNION SELECT password FROM credentials`
- UNION ALL: `SELECT 1 UNION ALL SELECT password FROM sys.sql_logins`
- UNION with type coercion: `SELECT CAST(1 AS varchar) UNION SELECT @@version`

### String Escaping / Quoting (~3 tests)
- Single quote escape: `SELECT * FROM users WHERE name = 'O''Brien'` (should pass -- valid SQL)
- Bracket injection in identifier: `SELECT * FROM [dbo].[users; DROP TABLE x]`
- Unicode escaping attempt

### T-SQL Specific (~4 tests)
- EXEC with string concat: `EXEC('DROP TABLE users')`
- xp_cmdshell: `EXEC xp_cmdshell 'dir'`
- OPENROWSET: `SELECT * FROM OPENROWSET('SQLNCLI', 'Server=evil', 'SELECT 1')`
- Bulk insert: `BULK INSERT users FROM '\\evil\share\data.csv'`

### Evasion Techniques (~4 tests)
- Mixed case: `SeLeCt * FrOm users; dRoP tAbLe users`
- Whitespace variations: `SELECT\t*\nFROM\tusers;\nDROP\tTABLE\tusers`
- IF-wrapped DML: `IF 1=1 BEGIN DELETE FROM users END`
- WAITFOR: `WAITFOR DELAY '00:00:10'; SELECT 1`

### Valid Queries That Must Pass (~3 tests)
- Column name containing SQL keyword: `SELECT [drop] FROM audit_log`
- CTE with keyword-like alias: `WITH delete_candidates AS (SELECT 1) SELECT * FROM delete_candidates`
- Multi-line formatted query: typical pretty-printed SELECT

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_validation_edge_cases.py tests/unit/test_identifier_validation.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | Column validation against metadata | unit | `uv run pytest tests/unit/test_identifier_validation.py -x` | Wave 0 |
| SEC-01 | Table/schema validation audit | unit | `uv run pytest tests/unit/test_query.py -x` | Existing (updated) |
| SEC-01 | Fail-open on metadata error | unit | `uv run pytest tests/unit/test_identifier_validation.py::test_fail_open -x` | Wave 0 |
| SEC-01 | Error message format | unit | `uv run pytest tests/unit/test_identifier_validation.py::test_error_messages -x` | Wave 0 |
| SEC-02 | sqlglot version pin test | unit | `uv run pytest tests/unit/test_validation_edge_cases.py::test_sqlglot_version -x` | Wave 0 |
| SEC-02 | Comment injection blocked | unit | `uv run pytest tests/unit/test_validation_edge_cases.py -k comment -x` | Wave 0 |
| SEC-02 | Batch injection blocked | unit | `uv run pytest tests/unit/test_validation_edge_cases.py -k batch -x` | Wave 0 |
| SEC-02 | T-SQL evasion blocked | unit | `uv run pytest tests/unit/test_validation_edge_cases.py -k tsql -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_validation_edge_cases.py tests/unit/test_identifier_validation.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_validation_edge_cases.py` -- covers SEC-02 (sqlglot edge cases + version assertion)
- [ ] `tests/unit/test_identifier_validation.py` -- covers SEC-01 (metadata-based validation)
- [ ] No framework install needed -- pytest already configured

## Open Questions

1. **Schema name validation depth**
   - What we know: `get_sample_data` accepts schema_name from user and embeds as `[{schema_name}]`. `list_schemas()` is available but heavier than column checks.
   - What's unclear: Whether to validate schema_name against `list_schemas()` or rely on SQL Server's own error for nonexistent schemas.
   - Recommendation: Don't validate schema separately in this phase. The table itself not existing will surface as a SQL error. Keep scope focused on the column validation path per CONTEXT.md priorities.

2. **MetadataService inspector cache lifetime**
   - What we know: SQLAlchemy inspector caches metadata until the inspector object is garbage collected. MetadataService creates inspector lazily.
   - What's unclear: In the MCP tool path, each `get_sample_data` call creates a new MetadataService (and thus new inspector). This means no cache benefit across calls.
   - Recommendation: Accept this for now. The inspector's per-call overhead is a single metadata query. Caching across calls is a performance optimization, not a security concern.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: src/db/query.py, src/db/metadata.py, src/db/validation.py, src/mcp_server/*.py
- sqlglot 29.0.1 behavior verified via local execution (Execute/ExecuteSql node handling)
- Existing test patterns from tests/unit/test_validation.py (142+ lines)

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions from user discussion session (2026-03-09)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, only pin tightening of existing library
- Architecture: HIGH - pattern (constructor injection) follows existing codebase conventions; MetadataService API already exists
- Pitfalls: HIGH - all identified from direct code inspection; fail-open pattern explicitly decided by user
- Surface area audit: HIGH - complete audit of all 9 MCP tools performed against actual source code

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable -- no fast-moving dependencies)
