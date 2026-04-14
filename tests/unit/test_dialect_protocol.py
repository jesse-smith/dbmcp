"""Tests for DialectStrategy protocol definition."""

from unittest.mock import MagicMock

from sqlalchemy.engine import Engine

from src.db.dialects.protocol import DialectStrategy


class _StubDialect:
    """Conforming stub implementing all DialectStrategy members."""

    @property
    def name(self) -> str:
        return "stub"

    @property
    def sqlglot_dialect(self) -> str:
        return "stub_dialect"

    @property
    def supports_indexes(self) -> bool:
        return True

    @property
    def has_fast_row_counts(self) -> bool:
        return False

    def create_engine(self, **kwargs) -> Engine:
        return MagicMock(spec=Engine)

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        return {}

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'


class _IncompleteDialect:
    """Non-conforming stub missing quote_identifier."""

    @property
    def name(self) -> str:
        return "incomplete"

    @property
    def sqlglot_dialect(self) -> str:
        return "incomplete"

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def has_fast_row_counts(self) -> bool:
        return False

    def create_engine(self, **kwargs) -> Engine:
        return MagicMock(spec=Engine)

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        return {}


class TestDialectStrategyConformance:
    """Test runtime_checkable protocol conformance."""

    def test_conforming_class_is_dialect_strategy(self) -> None:
        assert isinstance(_StubDialect(), DialectStrategy)

    def test_incomplete_class_is_not_dialect_strategy(self) -> None:
        assert not isinstance(_IncompleteDialect(), DialectStrategy)


class TestDialectStrategyProperties:
    """Test that protocol defines expected properties."""

    def test_name_returns_str(self) -> None:
        dialect = _StubDialect()
        result = dialect.name
        assert isinstance(result, str)
        assert result == "stub"

    def test_sqlglot_dialect_returns_str(self) -> None:
        dialect = _StubDialect()
        result = dialect.sqlglot_dialect
        assert isinstance(result, str)
        assert result == "stub_dialect"

    def test_supports_indexes_returns_bool(self) -> None:
        dialect = _StubDialect()
        result = dialect.supports_indexes
        assert isinstance(result, bool)
        assert result is True

    def test_has_fast_row_counts_returns_bool(self) -> None:
        dialect = _StubDialect()
        result = dialect.has_fast_row_counts
        assert isinstance(result, bool)
        assert result is False


class TestDialectStrategyMethods:
    """Test that protocol defines expected methods."""

    def test_create_engine_returns_engine(self) -> None:
        dialect = _StubDialect()
        result = dialect.create_engine(server="test", database="test")
        assert isinstance(result, Engine)

    def test_fast_row_counts_returns_dict(self) -> None:
        dialect = _StubDialect()
        engine = MagicMock(spec=Engine)
        result = dialect.fast_row_counts(engine)
        assert isinstance(result, dict)

    def test_fast_row_counts_accepts_schema_name(self) -> None:
        dialect = _StubDialect()
        engine = MagicMock(spec=Engine)
        result = dialect.fast_row_counts(engine, schema_name="dbo")
        assert isinstance(result, dict)

    def test_quote_identifier_returns_str(self) -> None:
        dialect = _StubDialect()
        result = dialect.quote_identifier("my_table")
        assert isinstance(result, str)
        assert result == '"my_table"'
