---
created: 2026-03-06T18:44:57.259Z
title: Fix identifier sanitization to use parameterized queries
area: database
files:
  - src/db/query.py:244
  - src/db/query.py:85-86
---

## Problem

`_sanitize_identifier()` in `src/db/query.py:244` uses a blocklist/regex approach to validate column names during column selection (called at line 85-86). This may accept identifiers containing SQL syntax characters if SQL Server allows them (e.g., bracket-delimited identifiers with embedded special characters).

This is a SQL injection surface — classified as **critical importance** in the concerns audit. The current approach relies on pattern matching rather than the database's own metadata to determine what's a valid identifier.

## Solution

Two complementary approaches:
1. **Validate against sys.columns metadata** before building queries — confirm the identifier actually exists as a column in the target table before incorporating it into SQL
2. **Use parameterized queries** instead of string interpolation for identifier sanitization where possible (though SQL Server doesn't support parameterized identifiers directly, SQLAlchemy's `quoted_name` or bracket-quoting can help)

At minimum, switch from blocklist to allowlist: only permit identifiers that match known columns from the metadata cache.
