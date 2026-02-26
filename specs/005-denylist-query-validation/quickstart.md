# Quickstart: Denylist Query Validation

**Feature**: 005-denylist-query-validation
**Date**: 2026-02-26

## What This Feature Does

Replaces the current keyword-based query blocklist with an AST-based denylist using `sqlglot`. This eliminates false positives (e.g., blocking a SELECT because a column is named "create_date") and enables allowing known-safe SQL Server stored procedures.

## Key Files to Modify

| File | Change |
|------|--------|
| `src/db/query.py` | Replace `_is_blocked_keyword()`, `parse_query_type()`, `is_query_allowed()` with `validate_query()` using sqlglot AST |
| `src/models/schema.py` | Add `DenialCategory` enum, `DenialReason` dataclass, `ValidationResult` dataclass; extend `Query` with `denial_reasons` field |
| `tests/unit/test_query.py` | Replace keyword/type tests with AST-based validation tests |
| `pyproject.toml` | Add `sqlglot` dependency |

## Key Design Decisions

1. **sqlglot** over sqlparse/sqloxide — typed AST with `.walk()`, pure Python, first-class T-SQL
2. **Denylist (not allowlist)** — unknown statement types are allowed by default
3. **Single validation pass** — replaces the current two-layer (keyword + type) approach
4. **22 safe stored procedures** hardcoded — sp_executesql explicitly excluded
5. **Fail-safe** — unparseable queries are denied

## Development Order

1. Add sqlglot dependency
2. Add new model types (DenialCategory, DenialReason, ValidationResult)
3. Implement `validate_query()` pure function with tests (TDD)
4. Integrate into `execute_query()` replacing old validation
5. Update existing tests, remove dead code
