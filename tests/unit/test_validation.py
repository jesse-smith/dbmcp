"""Unit tests for query validation (AST-based denylist).

Tests for validate_query() and denial categories, extracted from test_query.py
to match the src/db/validation.py module boundary.
"""

import pytest

from src.db.validation import validate_query
from src.models.schema import DenialCategory


class TestValidateQuerySafe:
    """T005: Tests for safe query validation -- queries that should pass."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "SELECT id, name FROM users WHERE active = 1",
            "SELECT create_date FROM orders",
            "SELECT execute_count FROM stats",
            "SELECT drop_reason FROM audit_log",
            "WITH cte AS (SELECT id FROM users) SELECT * FROM cte",
            "WITH a AS (SELECT 1 AS x), b AS (SELECT 2 AS y) SELECT * FROM a, b",
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM active_users)",
            "SELECT 1 AS x UNION SELECT 2 AS x",
        ],
        ids=[
            "simple_select",
            "select_with_where",
            "column_overlaps_create",
            "column_overlaps_execute",
            "column_overlaps_drop",
            "cte_select",
            "multiple_ctes_select",
            "select_with_subquery",
            "select_union",
        ],
    )
    def test_safe_query_passes(self, sql):
        """Safe queries pass validation."""
        result = validate_query(sql)
        assert result.is_safe is True

    def test_simple_select_no_reasons(self):
        """Plain SELECT passes with empty reasons list."""
        result = validate_query("SELECT * FROM users")
        assert result.is_safe is True
        assert result.reasons == []


class TestValidateQueryDenied:
    """T006: Tests for denied operations -- categorized denial reasons."""

    @pytest.mark.parametrize(
        "sql,category",
        [
            # DML
            ("INSERT INTO users (name) VALUES ('x')", DenialCategory.DML),
            ("UPDATE users SET name = 'x' WHERE id = 1", DenialCategory.DML),
            ("DELETE FROM users WHERE id = 1", DenialCategory.DML),
            (
                "MERGE INTO target USING source ON target.id = source.id "
                "WHEN MATCHED THEN UPDATE SET name = source.name",
                DenialCategory.DML,
            ),
            # DDL
            ("CREATE TABLE test (id INT)", DenialCategory.DDL),
            ("ALTER TABLE users ADD col INT", DenialCategory.DDL),
            ("DROP TABLE users", DenialCategory.DDL),
            ("TRUNCATE TABLE users", DenialCategory.DDL),
            # DCL
            ("GRANT SELECT ON users TO role1", DenialCategory.DCL),
            # Operational
            ("KILL 55", DenialCategory.OPERATIONAL),
            # SELECT INTO
            ("SELECT * INTO newtable FROM users", DenialCategory.SELECT_INTO),
            # CTE-wrapped writes
            (
                "WITH cte AS (SELECT 1 AS val) INSERT INTO t SELECT * FROM cte",
                DenialCategory.CTE_WRAPPED_WRITE,
            ),
            (
                "WITH cte AS (SELECT id, 'x' AS name FROM users) "
                "UPDATE t SET name = cte.name FROM t JOIN cte ON t.id = cte.id",
                DenialCategory.CTE_WRAPPED_WRITE,
            ),
            (
                "WITH old AS (SELECT id FROM users WHERE created < '2020-01-01') "
                "DELETE FROM users WHERE id IN (SELECT id FROM old)",
                DenialCategory.CTE_WRAPPED_WRITE,
            ),
            # Case variations (FR-013)
            ("drop table users", DenialCategory.DDL),
            ("Grant SELECT ON t TO r", DenialCategory.DCL),
            ("TRUNCATE table users", DenialCategory.DDL),
            # Stored procedures
            ("EXEC user_defined_proc", DenialCategory.STORED_PROCEDURE),
            ("EXEC unknown_proc", DenialCategory.STORED_PROCEDURE),
        ],
        ids=[
            "insert",
            "update",
            "delete",
            "merge",
            "create_table",
            "alter_table",
            "drop_table",
            "truncate",
            "grant",
            "kill",
            "select_into",
            "cte_insert",
            "cte_update",
            "cte_delete",
            "drop_lowercase",
            "grant_mixed_case",
            "truncate_mixed_case",
            "exec_user_defined",
            "exec_unknown",
        ],
    )
    def test_denied_with_category(self, sql, category):
        """Denied queries report the correct denial category."""
        result = validate_query(sql)
        assert result.is_safe is False
        assert len(result.reasons) >= 1
        assert result.reasons[0].category == category

    @pytest.mark.parametrize(
        "sql",
        [
            "REVOKE SELECT ON users FROM role1",
            "DENY SELECT ON users TO role1",
            "BACKUP DATABASE mydb TO DISK = 'path'",
            "RESTORE DATABASE mydb FROM DISK = 'path'",
        ],
        ids=["revoke", "deny", "backup", "restore"],
    )
    def test_unparseable_denied(self, sql):
        """Operations that sqlglot cannot parse are still denied."""
        result = validate_query(sql)
        assert result.is_safe is False


class TestValidateQueryAllowWrite:
    """T007: Tests for allow_write=True bypass behavior."""

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users (name) VALUES ('x')",
            "UPDATE users SET name = 'x'",
            "DELETE FROM users WHERE id = 1",
            (
                "MERGE INTO target USING source ON target.id = source.id "
                "WHEN MATCHED THEN UPDATE SET name = source.name"
            ),
        ],
        ids=["insert", "update", "delete", "merge"],
    )
    def test_dml_allowed_with_write(self, sql):
        """DML operations pass when allow_write=True."""
        result = validate_query(sql, allow_write=True)
        assert result.is_safe is True

    @pytest.mark.parametrize(
        "sql,category",
        [
            ("CREATE TABLE test (id INT)", DenialCategory.DDL),
            ("GRANT SELECT ON t TO r", DenialCategory.DCL),
            ("KILL 55", DenialCategory.OPERATIONAL),
            ("SELECT * INTO newtable FROM users", DenialCategory.SELECT_INTO),
        ],
        ids=["ddl_still_denied", "dcl_still_denied", "operational_still_denied", "select_into_still_denied"],
    )
    def test_non_dml_still_denied_with_write(self, sql, category):
        """Non-DML categories are NOT bypassed by allow_write."""
        result = validate_query(sql, allow_write=True)
        assert result.is_safe is False
        assert result.reasons[0].category == category


class TestStoredProcedureAllowlist:
    """T010: Tests for stored procedure allowlist (US3)."""

    @pytest.mark.parametrize("proc", [
        "sp_column_privileges", "sp_columns", "sp_databases", "sp_fkeys",
        "sp_pkeys", "sp_server_info", "sp_special_columns", "sp_sproc_columns",
        "sp_statistics", "sp_stored_procedures", "sp_table_privileges", "sp_tables",
        "sp_help", "sp_helptext", "sp_helpindex", "sp_helpconstraint",
        "sp_who", "sp_who2", "sp_spaceused",
        "sp_describe_first_result_set", "sp_describe_undeclared_parameters",
    ])
    def test_safe_procedure_allowed(self, proc):
        """Each of the 22 safe system procedures passes validation."""
        result = validate_query(f"EXEC {proc}")
        assert result.is_safe is True, f"{proc} should be safe but got: {result.reasons}"

    def test_safe_procedure_with_schema_prefix(self):
        """Multi-part name master.dbo.sp_help resolves correctly."""
        result = validate_query("EXEC master.dbo.sp_help")
        assert result.is_safe is True

    def test_safe_procedure_with_dbo_prefix(self):
        """dbo.sp_columns resolves correctly."""
        result = validate_query("EXEC dbo.sp_columns")
        assert result.is_safe is True

    def test_sp_executesql_denied(self):
        """sp_executesql is explicitly denied despite matching sp_ pattern."""
        result = validate_query("EXEC sp_executesql")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE
        assert "sp_executesql" in result.reasons[0].detail

    def test_unknown_procedure_denied(self):
        """User-defined procedures are denied."""
        result = validate_query("EXEC my_custom_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE

    def test_case_insensitive_sp_tables(self):
        """SP_TABLES (uppercase) matches case-insensitively."""
        result = validate_query("EXEC SP_TABLES")
        assert result.is_safe is True

    def test_case_insensitive_sp_help(self):
        """Sp_Help (mixed case) matches case-insensitively."""
        result = validate_query("EXEC Sp_Help")
        assert result.is_safe is True

    def test_execute_keyword(self):
        """EXECUTE (not just EXEC) works for safe procedures."""
        result = validate_query("EXECUTE sp_tables")
        assert result.is_safe is True

    def test_execute_unknown_denied(self):
        """EXECUTE unknown procedure is denied."""
        result = validate_query("EXECUTE unknown_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE


class TestObfuscationResistance:
    """T013: Tests for obfuscation resistance (US4)."""

    def test_batch_with_denied_statement(self):
        """A batch with one denied statement -> entire batch denied with statement_index."""
        result = validate_query("SELECT 1; DROP TABLE users")
        assert result.is_safe is False
        drop_reasons = [r for r in result.reasons if r.category == DenialCategory.DDL]
        assert len(drop_reasons) >= 1
        assert drop_reasons[0].statement_index == 1

    def test_batch_all_safe(self):
        """A batch of all safe statements passes."""
        result = validate_query("SELECT 1; SELECT 2")
        assert result.is_safe is True

    def test_batch_multiple_denied(self):
        """A batch with multiple denied statements reports all denials."""
        result = validate_query("DROP TABLE a; INSERT INTO b VALUES(1)")
        assert result.is_safe is False
        assert len(result.reasons) >= 2

    def test_begin_end_block_with_drop(self):
        """Denied operation inside BEGIN/END block detected."""
        result = validate_query("BEGIN DROP TABLE x END")
        assert result.is_safe is False

    def test_if_else_with_denied(self):
        """Denied operation inside IF/ELSE block detected."""
        result = validate_query("IF 1=1 DROP TABLE x")
        assert result.is_safe is False

    def test_while_with_denied(self):
        """Denied operation inside WHILE block detected."""
        result = validate_query("WHILE 1=1 DELETE FROM users")
        assert result.is_safe is False

    @pytest.mark.parametrize(
        "sql",
        [
            "THIS IS NOT VALID SQL !@#$%",
            "",
            "   \n\t  ",
        ],
        ids=["malformed_sql", "empty_query", "whitespace_only"],
    )
    def test_parse_failure_denied(self, sql):
        """Malformed, empty, and whitespace-only SQL is denied as PARSE_FAILURE."""
        result = validate_query(sql)
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.PARSE_FAILURE
