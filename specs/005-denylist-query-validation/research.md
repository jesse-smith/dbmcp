# Research: Denylist Query Validation

**Feature**: 005-denylist-query-validation
**Date**: 2026-02-26

## R1: Python SQL Parser Selection

**Decision**: Use `sqlglot` for AST-based query validation.

**Rationale**:
- First-class T-SQL dialect support (`dialect='tsql'`)
- Every SQL statement type maps to a distinct `exp.Expression` subclass (Select, Insert, Update, Delete, Create, Alter, Drop, Execute, Merge, Grant, Revoke, TruncateTable, Kill, Command)
- Built-in `.walk()` method for recursive AST traversal (finds nested denied types in CTEs, control flow blocks)
- Multi-statement batch parsing: `sqlglot.parse()` returns a list of AST nodes
- Pure Python, zero dependencies
- Very actively maintained (~8k GitHub stars, frequent releases)
- Performance adequate for single-query validation (microseconds per query)

**Alternatives considered**:
- `sqlparse`: Not a true AST — returns token tree. `EXEC` and `GRANT` return type `UNKNOWN`. Would require keyword-sniffing fallback, defeating the purpose.
- `sqloxide`: Fastest (5x faster than sqlglot), Rust bindings for sqlparser-rs (same parser as dbtoon reference). Tradeoffs: native dependency, untyped dict AST, no built-in `.walk()`, less actively maintained Python bindings. Only preferable at high-throughput scale (not our use case).
- `python-sqlparser`: Abandoned, not a real contender.

## R2: Validation Architecture Pattern

**Decision**: Replace the two-layer validation (keyword blocklist + query type check) with a single AST-based validation pass.

**Rationale**:
- Current keyword-based approach is brittle: false positives on column names containing blocked words (e.g., `execute_count`, `create_date`)
- AST-based validation operates on parsed structure, not text tokens — inherently immune to keyword overlap false positives
- Comment stripping becomes unnecessary: the parser ignores comments during AST construction
- Single-pass validation is simpler than the current two-layer approach

**Current flow** (to be replaced):
1. `_is_blocked_keyword()` — regex tokenize, check frozenset
2. `parse_query_type()` — first-keyword heuristic
3. `is_query_allowed()` — type-based allow/deny

**New flow**:
1. `sqlglot.parse(sql, dialect='tsql')` — produces AST node list
2. Walk each node: `isinstance(stmt, DENIED_TYPES)` — categorized deny
3. For `Execute` nodes: check procedure name against safe allowlist

## R3: Stored Procedure Allowlist Strategy

**Decision**: Hardcoded frozenset of 22 canonical procedure names, checked case-insensitively against the last identifier part of multi-part names.

**Rationale**:
- Matches the dbtoon reference implementation approach
- The safe procedure list is well-established SQL Server system procedures — changes are rare
- Multi-part name resolution (e.g., `master.dbo.sp_help` → `sp_help`) needed because SQL Server allows schema-qualified procedure calls
- `sp_executesql` explicitly excluded despite matching `sp_` pattern — it executes arbitrary SQL

## R4: Backward Compatibility with allow_write

**Decision**: When `allow_write=True`, DML writes (INSERT, UPDATE, DELETE, MERGE) bypass the denylist. All other denied categories (DDL, DCL, Operational, etc.) remain denied regardless of `allow_write`.

**Rationale**:
- Preserves existing behavior for current consumers
- DDL/DCL/Operational commands are dangerous even in "write mode" — they modify schema/permissions, not just data
- MERGE included per clarification session decision

## R5: Fail-Safe on Parse Failure

**Decision**: Queries that fail to parse are denied with a `ParseFailure` category.

**Rationale**:
- If the parser can't understand the query, we can't verify it's safe
- Matches dbtoon reference behavior
- sqlglot raises `sqlglot.errors.ParseError` on invalid SQL — straightforward to catch
