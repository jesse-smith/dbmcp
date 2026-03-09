# Phase 5: Security Hardening - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Query validation catches edge cases that the current regex/blocklist approach misses. Identifier sanitization is upgraded from regex pattern matching to metadata-based validation against actual database objects. sqlglot is pinned to a tested version range with dedicated edge case fixtures proving it handles the project's security needs.

</domain>

<decisions>
## Implementation Decisions

### Identifier validation scope
- Validate all user-supplied identifiers: columns, table names, and schema names against actual database metadata
- Only user-supplied identifiers (from MCP tool parameters) require validation — internally-sourced identifiers (e.g., column names returned from sys.columns by analysis tools) are trusted
- Primary focus is get_sample_data (only tool with user-supplied columns param) plus table/schema validation across tools — a quick audit confirms the full surface area but get_sample_data is the main target
- Replace the current regex-based `_sanitize_identifier()` entirely with metadata lookup — no regex as first pass, metadata is the single source of truth
- If metadata lookup fails (e.g., permission denied on sys.tables), fail open: fall back to the existing regex check and log a warning. Don't break working queries because of metadata access issues.

### Validation failure behavior
- When an identifier fails metadata validation, reject the entire tool call with an error — no partial execution
- Error message names the invalid identifier specifically: "Column 'foobar' does not exist in [dbo].[Users]" — don't list valid alternatives
- Comparison is case-insensitive (matching SQL Server default collation behavior) — 'userName' matches 'UserName' in sys.columns

### Validation architecture
- Validation lives inside QueryService (centralized), not at the MCP tool layer — any code path that builds SQL goes through validation automatically
- Inject MetadataService into QueryService via constructor to provide metadata access
- Reuse MetadataService's existing cache (no fresh queries per validation) — accept minor staleness risk for performance
- Service wiring approach (factory vs direct plumbing in tool functions) is Claude's discretion

### sqlglot version pinning
- Tighten pin from `>=26.0.0,<30.0.0` to `>=29.0.0,<30.0.0` in pyproject.toml
- Add a test that asserts `sqlglot.__version__` >= 29.0.0 — documents the dependency floor and catches accidental downgrades
- The v29 floor matters because Execute node handling changed (exp.Execute vs exp.Command for EXEC/EXECUTE)

### Edge case test fixtures
- ~20-30 focused, practical test cases targeting real-world attack patterns: comment injection (--), semicolon batching, UNION injection, string escaping, T-SQL evasion, comment obfuscation
- Separate dedicated test file (not merged into existing test_validation.py) — keeps edge cases isolated and easy to extend
- Fixtures test sqlglot query parsing only — identifier validation gets its own tests elsewhere
- Not a comprehensive catalog (50+ OWASP patterns) — focused on patterns sqlglot actually needs to handle for this project

### Claude's Discretion
- Service wiring approach: factory pattern vs direct MetadataService injection in each tool function
- Exact edge case selection for the ~20-30 fixture set (prioritize patterns most relevant to read-only SQL Server access)
- Test file organization for identifier validation tests (new file vs extending existing test_query.py)
- How to handle the MetadataService dependency in QueryService tests (mock vs test fixtures)

</decisions>

<specifics>
## Specific Ideas

- User explicitly wants metadata as single source of truth — no regex layering. "Replace regex with metadata" was the clear preference.
- Fail-open on metadata errors was chosen for usability: "Don't break working queries because of a metadata access issue"
- Case-insensitive matching matches SQL Server default — user acknowledged case-sensitive collations are rare enough to not design for

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MetadataService` (src/db/metadata.py): Already has `get_tables()`, `get_columns()` with caching. Can be injected into QueryService for validation.
- `QueryService._sanitize_identifier()` (src/db/query.py:231-254): Current regex approach to be replaced. Bracket-quoting logic (`[identifier]`) is still needed after validation.
- `validate_query()` (src/db/validation.py): Existing sqlglot-based validation. Edge case fixtures will test this function.
- `test_validation.py`: 142+ lines of existing validation tests. New edge case file follows same patterns but stays separate.

### Established Patterns
- QueryService takes `engine` at construction (query.py). Adding `metadata_service` parameter follows the same injection pattern.
- Analysis modules (column_stats, pk_discovery, fk_candidates) embed identifiers from metadata results — these are trusted internal sources and won't be changed.
- Parametrized test patterns in test_validation.py — edge case file should follow the same `@pytest.mark.parametrize` style.

### Integration Points
- `QueryService.__init__()` — constructor signature changes to accept optional MetadataService
- `QueryService._sanitize_identifier()` — replaced with metadata-based validation
- `pyproject.toml` line 29 — sqlglot pin tightened
- MCP tool functions in schema_tools.py/query_tools.py — may need to pass MetadataService when creating QueryService

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-security-hardening*
*Context gathered: 2026-03-09*
