"""Unit tests for catalog-aware raw-SQL reflection (CatalogAwareReflector).

These tests are catalog-discriminating: the fake connection only returns rows
when the executed SQL carries the expected three-part backtick-quoted name. A
catalog that never reaches the SQL therefore yields empty results, proving the
reflector threads the requested catalog into the raw DESCRIBE TABLE / SHOW
TABLES statements (IDENT-08).
"""

from unittest.mock import MagicMock

import pytest

from src.analysis._sql import CatalogAwareReflector


def _result(rows):
    """Build a mock SQLAlchemy result whose fetchall() yields ``rows``."""
    res = MagicMock()
    res.fetchall.return_value = rows
    return res


def _discriminating_connection(expected_fragment: str, rows):
    """A fake connection whose execute() returns ``rows`` only when the SQL
    string contains ``expected_fragment`` (the 3-part backtick name); else []."""
    conn = MagicMock()

    def _execute(stmt, *args, **kwargs):
        sql = str(stmt)
        if expected_fragment in sql:
            return _result(rows)
        return _result([])

    conn.execute.side_effect = _execute
    return conn


def _executed_sql(conn) -> list[str]:
    """All SQL strings the reflector executed against ``conn``."""
    return [str(call.args[0]) for call in conn.execute.call_args_list]


@pytest.mark.dialects("databricks")
class TestCatalogAwareReflectorColumns:
    """reflect_columns() — catalog-scoped DESCRIBE TABLE."""

    def test_describe_table_carries_three_part_backtick_name(self, dialect):
        """DESCRIBE TABLE SQL contains `catalog`.`schema`.`table` (all quoted)."""
        conn = _discriminating_connection(
            "`cerner_src`.`dbo`.`orders`",
            [("id", "int"), ("amount", "double")],
        )
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        cols = reflector.reflect_columns(
            catalog="cerner_src", schema="dbo", table="orders"
        )

        sql = _executed_sql(conn)[0]
        assert "DESCRIBE TABLE" in sql
        assert "`cerner_src`.`dbo`.`orders`" in sql
        assert cols  # non-empty -> the right name reached the SQL

    def test_catalog_discriminates_results(self, dialect):
        """If the requested catalog doesn't reach the SQL, no rows come back.

        The fake only returns rows for `cerner_src`; asking for a different
        catalog must yield [] -- this proves the catalog is threaded into SQL.
        """
        conn = _discriminating_connection(
            "`cerner_src`.`dbo`.`orders`",
            [("id", "int")],
        )
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        right = reflector.reflect_columns(
            catalog="cerner_src", schema="dbo", table="orders"
        )
        wrong = reflector.reflect_columns(
            catalog="other_cat", schema="dbo", table="orders"
        )

        assert right  # catalog reached the SQL
        assert wrong == []  # different catalog -> no match -> empty

    def test_parses_describe_output_like_metadata(self, dialect):
        """col=row[0], type=row[1]; STOP at blank col_name or '#' marker."""
        rows = [
            ("id", "int"),
            ("name", "string"),
            ("", ""),  # blank separator -> stop here
            ("# Partition Information", ""),
            ("part_col", "string"),
        ]
        conn = _discriminating_connection("`c`.`s`.`t`", rows)
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        cols = reflector.reflect_columns(catalog="c", schema="s", table="t")

        assert cols == [
            {"name": "id", "data_type": "int"},
            {"name": "name", "data_type": "string"},
        ]

    def test_stops_at_hash_marker_directly(self, dialect):
        """A '#'-prefixed col_name halts parsing even without a blank row."""
        rows = [
            ("col_a", "string"),
            ("# Detailed Table Information", ""),
            ("Owner", "root"),
        ]
        conn = _discriminating_connection("`c`.`s`.`t`", rows)
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        cols = reflector.reflect_columns(catalog="c", schema="s", table="t")

        assert cols == [{"name": "col_a", "data_type": "string"}]


@pytest.mark.dialects("databricks")
class TestCatalogAwareReflectorTables:
    """list_tables() — catalog-scoped SHOW TABLES IN."""

    def test_show_tables_carries_two_part_backtick_name(self, dialect):
        """SHOW TABLES IN `catalog`.`schema`; returns tableName from row[1]."""
        conn = _discriminating_connection(
            "`cerner_src`.`dbo`",
            [
                ("dbo", "orders", False),
                ("dbo", "customers", False),
            ],
        )
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        tables = reflector.list_tables(catalog="cerner_src", schema="dbo")

        sql = _executed_sql(conn)[0]
        assert "SHOW TABLES IN" in sql
        assert "`cerner_src`.`dbo`" in sql
        assert tables == ["orders", "customers"]

    def test_list_tables_catalog_discriminates(self, dialect):
        """A non-matching catalog yields no tables."""
        conn = _discriminating_connection(
            "`cerner_src`.`dbo`",
            [("dbo", "orders", False)],
        )
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        assert reflector.list_tables(catalog="cerner_src", schema="dbo") == [
            "orders"
        ]
        assert reflector.list_tables(catalog="elsewhere", schema="dbo") == []


@pytest.mark.dialects("databricks")
class TestCatalogAwareReflectorStateless:
    """Statelessness + injection-safety guards."""

    def test_never_emits_use_catalog(self, dialect):
        """No executed SQL string may contain USE CATALOG (stateless)."""
        conn = _discriminating_connection(
            "`c`.`s`.`t`", [("id", "int")]
        )
        reflector = CatalogAwareReflector(conn, dialect.dialect)
        reflector.reflect_columns(catalog="c", schema="s", table="t")
        reflector.list_tables(catalog="c", schema="s")

        for sql in _executed_sql(conn):
            assert "USE CATALOG" not in sql.upper()

    def test_identifiers_are_quoted_not_raw(self, dialect):
        """Segments with a dot/backtick go through quote_identifier, not raw
        concatenation -- the injection control (T-15.1-01)."""
        # A schema containing a dot would, if unquoted, expand the dotted name.
        conn = _discriminating_connection("ZZZ_never_matches", [])
        reflector = CatalogAwareReflector(conn, dialect.dialect)

        reflector.reflect_columns(
            catalog="cat", schema="evil.schema", table="tbl"
        )

        sql = _executed_sql(conn)[0]
        # The real Databricks dialect quote_identifier wraps the whole segment
        # in backticks, so the dotted schema appears as a single quoted token.
        assert "`evil.schema`" in sql
        # And it must NOT appear as a raw unquoted dotted segment.
        assert ".evil.schema." not in sql
