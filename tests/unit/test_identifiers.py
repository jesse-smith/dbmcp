"""Unit tests for the cross-dialect identifier resolver.

Exhaustive parametrized matrix (D-12) covering dialect x depth x
conflict/agreement/catalog-gate for resolve_identifier(), the frozen
ResolvedIdentifier dataclass, and the shared _assert_catalog_allowed gate.

Uses real dialect instances (MssqlDialect, DatabricksDialect, GenericDialect)
rather than mocks -- the resolver only reads cheap @property values.
"""

import dataclasses

import pytest

from src.db.dialects.databricks import DatabricksDialect
from src.db.dialects.generic import GenericDialect
from src.db.dialects.mssql import MssqlDialect
from src.db.identifiers import (
    CATALOG_GATE_MESSAGE,
    ResolvedIdentifier,
    _assert_catalog_allowed,
    resolve_identifier,
)


class TestDepthParsing:
    """IDENT-03: dialect-aware depth parsing via len(parts), not attributes."""

    @pytest.mark.parametrize(
        ("dialect", "table_name", "expected"),
        [
            (
                MssqlDialect(),
                "sales.orders",
                ResolvedIdentifier(catalog=None, schema="sales", table="orders"),
            ),
            (
                MssqlDialect(),
                "orders",
                ResolvedIdentifier(catalog=None, schema="dbo", table="orders"),
            ),
            (
                DatabricksDialect(),
                "cat.sales.orders",
                ResolvedIdentifier(catalog="cat", schema="sales", table="orders"),
            ),
            (
                DatabricksDialect(),
                "sales.orders",
                ResolvedIdentifier(catalog=None, schema="sales", table="orders"),
            ),
            (
                GenericDialect(),
                "orders",
                ResolvedIdentifier(catalog=None, schema=None, table="orders"),
            ),
        ],
        ids=[
            "mssql_two_part",
            "mssql_one_part_default_schema",
            "databricks_three_part",
            "databricks_two_part",
            "generic_one_part",
        ],
    )
    def test_depth_parsing_ok(self, dialect, table_name, expected):
        result = resolve_identifier(table_name, None, None, dialect)
        assert result == expected

    @pytest.mark.parametrize(
        ("dialect", "table_name", "expected_fragment"),
        [
            (MssqlDialect(), "a.b.c", "at most 2 parts"),
            (DatabricksDialect(), "a.b.c.d", "at most 3 parts"),
            (GenericDialect(), "a.b", "at most 1"),
        ],
        ids=[
            "mssql_three_parts_over_depth",
            "databricks_four_parts_over_depth",
            "generic_two_parts_over_depth",
        ],
    )
    def test_depth_parsing_over_depth_raises(
        self, dialect, table_name, expected_fragment
    ):
        with pytest.raises(ValueError, match=expected_fragment):
            resolve_identifier(table_name, None, None, dialect)

    @pytest.mark.parametrize(
        ("dialect", "table_name"),
        [
            (MssqlDialect(), "[my.table]"),
            (DatabricksDialect(), "`my.table`"),
        ],
        ids=["mssql_bracket_quoted", "databricks_backtick_quoted"],
    )
    def test_quoted_dotted_name_is_one_part(self, dialect, table_name):
        result = resolve_identifier(table_name, None, None, dialect)
        assert result.table == "my.table"


class TestConflictDetection:
    """IDENT-04, D-04: disagreement raises; redundant-but-consistent is allowed."""

    def test_mssql_schema_agreement_ok(self):
        result = resolve_identifier("sales.orders", "sales", None, MssqlDialect())
        assert result.schema == "sales"
        assert result.table == "orders"

    def test_mssql_schema_conflict_raises(self):
        with pytest.raises(ValueError, match="schema"):
            resolve_identifier("sales.orders", "hr", None, MssqlDialect())

    def test_databricks_catalog_agreement_ok(self):
        result = resolve_identifier(
            "cat.sales.orders", None, "cat", DatabricksDialect()
        )
        assert result.catalog == "cat"
        assert result.schema == "sales"

    def test_databricks_catalog_conflict_raises(self):
        with pytest.raises(ValueError, match="catalog"):
            resolve_identifier("cat.sales.orders", None, "other", DatabricksDialect())


class TestCatalogGate:
    """D-07: catalog gate fires when dialect.max_identifier_depth < 3."""

    @pytest.mark.parametrize(
        "dialect",
        [MssqlDialect(), GenericDialect()],
        ids=["mssql", "generic"],
    )
    def test_catalog_on_shallow_dialect_raises(self, dialect):
        with pytest.raises(ValueError):
            resolve_identifier("orders", None, "x", dialect)

    def test_catalog_gate_fires_before_depth_check(self):
        # Catalog passed on a shallow dialect must report the catalog-gate
        # message, NOT a depth-parsing error.
        with pytest.raises(ValueError) as exc_info:
            resolve_identifier("orders", None, "x", MssqlDialect())
        assert "at most" not in str(exc_info.value)

    def test_catalog_on_databricks_ok(self):
        result = resolve_identifier("orders", None, "x", DatabricksDialect())
        assert result.catalog == "x"
        assert result.schema is None
        assert result.table == "orders"

    def test_catalog_none_no_gate(self):
        result = resolve_identifier("orders", None, None, MssqlDialect())
        assert result.table == "orders"

    def test_assert_catalog_allowed_shallow_raises(self):
        with pytest.raises(ValueError):
            _assert_catalog_allowed("x", MssqlDialect())

    def test_assert_catalog_allowed_none_no_raise(self):
        _assert_catalog_allowed(None, MssqlDialect())

    def test_assert_catalog_allowed_databricks_no_raise(self):
        _assert_catalog_allowed("x", DatabricksDialect())

    def test_catalog_gate_message_is_module_level(self):
        # The shared template must be a module-level constant so table_name-less
        # tools (list_schemas, find_pk/fk_candidates) reuse the exact phrasing.
        assert isinstance(CATALOG_GATE_MESSAGE, str)
        assert "{" in CATALOG_GATE_MESSAGE


class TestDefaultSchema:
    """IDENT-07, D-08/D-10: missing schema filled from dialect.default_schema."""

    def test_mssql_default_schema_dbo(self):
        result = resolve_identifier("orders", None, None, MssqlDialect())
        assert result.schema == "dbo"

    def test_generic_no_synthetic_fallback(self):
        result = resolve_identifier("orders", None, None, GenericDialect())
        assert result.schema is None

    def test_databricks_no_default_schema(self):
        result = resolve_identifier("orders", None, None, DatabricksDialect())
        assert result.schema is None


class TestMalformedInput:
    """RESEARCH A1: sqlglot.ParseError normalized to ValueError."""

    @pytest.mark.parametrize(
        "table_name",
        ["", "a."],
        ids=["empty", "trailing_dot"],
    )
    def test_malformed_table_name_raises_value_error(self, table_name):
        with pytest.raises(ValueError):
            resolve_identifier(table_name, None, None, GenericDialect())


class TestResolvedIdentifier:
    """D-02: ResolvedIdentifier is a frozen dataclass with required fields."""

    def test_is_frozen(self):
        ident = ResolvedIdentifier(catalog=None, schema="dbo", table="orders")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ident.table = "other"  # type: ignore[misc]
