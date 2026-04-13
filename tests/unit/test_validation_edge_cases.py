"""Edge case tests for sqlglot-based query validation.

Validates the pinned sqlglot version handles security-critical edge cases:
comment injection, semicolon batching, UNION injection, string escaping,
T-SQL evasion techniques, and valid query passthrough.

SEC-02: ~25 parametrized tests organized by attack category.
"""

import pytest

from src.db.validation import validate_query
from src.models.schema import DenialCategory


class TestCommentInjection:
    """Comment-based attack patterns. SQL comments strip dangerous text from execution."""

    @pytest.mark.parametrize(
        "sql,expected_safe",
        [
            # Single-line comment hides DROP -- it's in the comment, so safe
            ("SELECT * FROM users -- DROP TABLE users", True),
            # Multi-line comment wrapping dangerous SQL -- comment, so safe
            ("SELECT 1 /* DROP TABLE users */", True),
            # Nested comments -- still a comment, safe
            ("SELECT /* /* nested */ */ 1 FROM t", True),
            # Comment between keywords -- valid SELECT, safe
            ("SELECT /* comment */ * FROM users", True),
        ],
        ids=[
            "single_line_comment_hides_drop",
            "multiline_comment_wraps_drop",
            "nested_comment",
            "comment_between_keywords",
        ],
    )
    def test_comment_injection(self, sql, expected_safe):
        """Comments strip dangerous text -- commented-out SQL is not executable."""
        result = validate_query(sql)
        assert result.is_safe is expected_safe


class TestSemicolonBatching:
    """Semicolon-separated batch injection. Multi-statement = denied."""

    @pytest.mark.parametrize(
        "sql",
        [
            # Simple batch: safe SELECT + dangerous DROP
            "SELECT 1; DROP TABLE users",
            # Whitespace around semicolon
            "SELECT 1 ;   DROP TABLE x",
            # Comment between statements
            "SELECT 1; /* comment */ DROP TABLE x",
            # Triple batch: two safe + one dangerous
            "SELECT 1; SELECT 2; DROP TABLE x",
        ],
        ids=[
            "simple_batch_with_drop",
            "whitespace_batch_with_drop",
            "comment_separated_batch",
            "triple_batch_with_drop",
        ],
    )
    def test_batch_injection_denied(self, sql):
        """Batches containing dangerous statements are denied."""
        result = validate_query(sql)
        assert result.is_safe is False
        ddl_reasons = [r for r in result.reasons if r.category == DenialCategory.DDL]
        assert len(ddl_reasons) >= 1


class TestUnionInjection:
    """UNION-based query patterns. UNION SELECT is valid read-only SQL."""

    @pytest.mark.parametrize(
        "sql",
        [
            # Basic UNION
            "SELECT id FROM users UNION SELECT id FROM admins",
            # UNION ALL
            "SELECT 1 AS x UNION ALL SELECT 2 AS x",
            # UNION with type coercion (CAST)
            "SELECT id FROM users UNION SELECT CAST(name AS INT) FROM users",
        ],
        ids=[
            "basic_union",
            "union_all",
            "union_with_type_coercion",
        ],
    )
    def test_union_queries_pass(self, sql):
        """UNION SELECT is a valid read-only pattern and must pass."""
        result = validate_query(sql)
        assert result.is_safe is True


class TestStringEscaping:
    """String escaping and identifier quoting edge cases."""

    @pytest.mark.parametrize(
        "sql,expected_safe",
        [
            # Valid single-quote escape passes (O'Brien)
            ("SELECT * FROM users WHERE name = 'O''Brien'", True),
            # Bracket-quoted identifier containing SQL keywords -- safe
            ("SELECT [DROP TABLE users] FROM t", True),
            # Unicode string literal (N prefix) -- safe
            ("SELECT * FROM users WHERE name = N'test'", True),
        ],
        ids=[
            "single_quote_escape",
            "bracket_identifier_injection",
            "unicode_string_literal",
        ],
    )
    def test_string_escaping(self, sql, expected_safe):
        """String escaping and identifier quoting must not cause false positives."""
        result = validate_query(sql)
        assert result.is_safe is expected_safe


class TestTSQLSpecific:
    """T-SQL specific dangerous operations."""

    @pytest.mark.parametrize(
        "sql",
        [
            # EXEC with string concatenation (parse failure = denied)
            "EXEC('SELECT ' + '1')",
            # xp_cmdshell (stored procedure not in allowlist)
            "EXEC xp_cmdshell 'dir'",
            # BULK INSERT (parse failure = denied)
            "BULK INSERT t FROM 'file.csv'",
            # WAITFOR DELAY (parse failure = denied)
            "WAITFOR DELAY '00:00:05'",
        ],
        ids=[
            "exec_string_concat",
            "xp_cmdshell",
            "bulk_insert",
            "waitfor_delay",
        ],
    )
    def test_tsql_dangerous_denied(self, sql):
        """T-SQL specific dangerous operations must be denied."""
        result = validate_query(sql)
        assert result.is_safe is False

    def test_xp_cmdshell_category(self):
        """xp_cmdshell is denied as a stored procedure not in the allowlist."""
        result = validate_query("EXEC xp_cmdshell 'dir'")
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE


class TestEvasionTechniques:
    """Evasion techniques: casing, whitespace, control flow wrapping."""

    @pytest.mark.parametrize(
        "sql,category",
        [
            # Mixed case DML
            ("iNsErT INTO users (name) VALUES (1)", DenialCategory.DML),
            # Extra whitespace in DML
            ("DELETE    FROM    users    WHERE    id = 1", DenialCategory.DML),
            # IF-wrapped DML
            ("IF 1=1 INSERT INTO t VALUES(1)", DenialCategory.DML),
            # WHILE-wrapped DML (sqlglot doesn't fully parse WHILE body, denied conservatively)
            ("WHILE 1=1 DELETE FROM users", DenialCategory.OPERATIONAL),
        ],
        ids=[
            "mixed_case_dml",
            "whitespace_variation_dml",
            "if_wrapped_dml",
            "while_wrapped_dml",
        ],
    )
    def test_evasion_denied(self, sql, category):
        """Evasion techniques (casing, whitespace, control flow) must be denied."""
        result = validate_query(sql)
        assert result.is_safe is False
        assert result.reasons[0].category == category


class TestValidQueriesPassthrough:
    """Valid queries that must NOT trigger false positives."""

    @pytest.mark.parametrize(
        "sql",
        [
            # Column names that are SQL keywords (bracket-quoted)
            "SELECT [insert], [update], [delete] FROM audit_log",
            # CTE with keyword-like alias
            "WITH [delete] AS (SELECT 1 AS x) SELECT * FROM [delete]",
            # Multi-line formatted SELECT
            """
            SELECT
                id,
                name,
                email
            FROM
                users
            WHERE
                active = 1
            ORDER BY
                name
            """,
        ],
        ids=[
            "columns_named_after_keywords",
            "cte_with_keyword_alias",
            "multiline_formatted_select",
        ],
    )
    def test_valid_queries_pass(self, sql):
        """Valid read-only queries must pass without false positives."""
        result = validate_query(sql)
        assert result.is_safe is True
