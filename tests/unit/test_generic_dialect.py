"""Tests for GenericDialect protocol compliance and behavior."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine

from src.db.dialects.generic import GenericDialect, _URL_SCHEME_TO_SQLGLOT
from src.db.dialects.protocol import DialectStrategy


class TestGenericDialectProtocol:
    """Verify GenericDialect satisfies DialectStrategy protocol."""

    def test_isinstance_check(self):
        """GenericDialect satisfies the runtime_checkable DialectStrategy protocol."""
        dialect = GenericDialect()
        assert isinstance(dialect, DialectStrategy)

    def test_name_returns_generic(self):
        assert GenericDialect().name == "generic"

    def test_sqlglot_dialect_with_value(self):
        """Returns the value passed to constructor."""
        dialect = GenericDialect(sqlglot_dialect_name="postgres")
        assert dialect.sqlglot_dialect == "postgres"

    def test_sqlglot_dialect_default_none(self):
        """Returns None when no mapping exists."""
        dialect = GenericDialect()
        assert dialect.sqlglot_dialect is None

    def test_supports_indexes(self):
        assert GenericDialect().supports_indexes is True

    def test_has_fast_row_counts(self):
        assert GenericDialect().has_fast_row_counts is False

    def test_safe_procedures_empty(self):
        result = GenericDialect().safe_procedures
        assert result == frozenset()
        assert isinstance(result, frozenset)

    def test_quote_identifier_ansi(self):
        """ANSI double-quote wrapping."""
        assert GenericDialect().quote_identifier("my_col") == '"my_col"'

    def test_quote_identifier_with_spaces(self):
        assert GenericDialect().quote_identifier("my col") == '"my col"'


class TestGenericDialectEngine:
    """Verify create_engine behavior."""

    def test_create_engine_returns_engine(self):
        engine = GenericDialect().create_engine(sqlalchemy_url="sqlite:///")
        assert isinstance(engine, Engine)
        engine.dispose()

    def test_create_engine_pool_pre_ping(self):
        engine = GenericDialect().create_engine(sqlalchemy_url="sqlite:///")
        # SQLAlchemy 2.x stores pre_ping on pool
        assert engine.pool._pre_ping is True
        engine.dispose()

    def test_fast_row_counts_returns_empty_dict(self):
        engine = GenericDialect().create_engine(sqlalchemy_url="sqlite:///")
        result = GenericDialect().fast_row_counts(engine)
        assert result == {}
        engine.dispose()

    def test_fast_row_counts_with_schema(self):
        engine = GenericDialect().create_engine(sqlalchemy_url="sqlite:///")
        result = GenericDialect().fast_row_counts(engine, schema_name="public")
        assert result == {}
        engine.dispose()


class TestUrlSchemeMapping:
    """Verify the URL scheme to sqlglot mapping dict."""

    def test_postgresql_mapping(self):
        assert _URL_SCHEME_TO_SQLGLOT["postgresql"] == "postgres"

    def test_mysql_mapping(self):
        assert _URL_SCHEME_TO_SQLGLOT["mysql"] == "mysql"

    def test_sqlite_mapping(self):
        assert _URL_SCHEME_TO_SQLGLOT["sqlite"] == "sqlite"

    def test_unknown_scheme_not_in_mapping(self):
        assert "oracle" not in _URL_SCHEME_TO_SQLGLOT


class TestGenericDialectSampleQueries:
    """Generic dialect builds LIMIT-based sample queries (never TOP/TABLESAMPLE)."""

    def test_build_sample_query_top_emits_limit(self):
        from src.models.schema import SamplingMethod
        sql = GenericDialect().build_sample_query(
            SamplingMethod.TOP, '"public"."t"', "*", 5
        )
        assert 'SELECT * FROM "public"."t"' in sql
        assert "LIMIT 5" in sql
        assert "TOP (" not in sql
        assert "TABLESAMPLE" not in sql

    def test_build_sample_query_tablesample_uses_random_limit(self):
        from src.models.schema import SamplingMethod
        sql = GenericDialect().build_sample_query(
            SamplingMethod.TABLESAMPLE, '"public"."t"', "*", 5
        )
        assert "ORDER BY RANDOM()" in sql
        assert "LIMIT 5" in sql
        assert "TABLESAMPLE" not in sql
        assert "TOP (" not in sql

    def test_build_sample_query_modulo_uses_row_number_with_limit(self):
        from src.models.schema import SamplingMethod
        sql = GenericDialect().build_sample_query(
            SamplingMethod.MODULO, '"public"."t"', "*", 5
        )
        assert "ROW_NUMBER() OVER" in sql
        assert "LIMIT 5" in sql
        assert "TOP (" not in sql

    def test_build_sample_query_modulo_sqlite_uses_rowid(self):
        from src.models.schema import SamplingMethod
        sql = GenericDialect(sqlglot_dialect_name="sqlite").build_sample_query(
            SamplingMethod.MODULO, "t", "*", 5
        )
        assert "ROW_NUMBER() OVER" in sql
        assert "ORDER BY ROWID" in sql
        assert "LIMIT 5" in sql
