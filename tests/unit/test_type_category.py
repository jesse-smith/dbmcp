"""Unit tests for the shared cross-dialect type categorizer (UE-01).

``type_category`` was extracted from ``ColumnStatsCollector._get_type_category``
into ``src/analysis/_sql.py`` so the FK candidate search can reuse it to skip
type-incompatible overlap comparisons. These tests lock the cross-dialect string
classification the FK filter depends on, plus the isinstance behavior that
column_stats delegation must preserve.
"""

import pytest
from sqlalchemy import types as sa_types

from src.analysis._sql import type_category


class TestTypeCategoryStringPath:
    """String classification across dialects (the FK-filter path)."""

    @pytest.mark.parametrize(
        "data_type",
        ["int", "bigint", "smallint", "tinyint", "decimal", "numeric",
         "float", "real", "money", "smallmoney",  # MSSQL
         "integer", "double", "long",             # Databricks / generic
         "DECIMAL(10,2)", "BIGINT", "Double"],     # params + casing
    )
    def test_numeric_types(self, data_type):
        assert type_category(data_type) == "numeric"

    @pytest.mark.parametrize(
        "data_type",
        ["date", "datetime", "datetime2", "smalldatetime", "datetimeoffset",
         "time", "timestamp", "TIMESTAMP", "Date"],
    )
    def test_datetime_types(self, data_type):
        assert type_category(data_type) == "datetime"

    @pytest.mark.parametrize(
        "data_type",
        ["char", "varchar", "text", "nchar", "nvarchar", "ntext",  # MSSQL
         "string", "STRING",                                        # Databricks
         "VARCHAR(50)", "nvarchar(255)", "Char"],                    # params + casing
    )
    def test_string_types(self, data_type):
        assert type_category(data_type) == "string"

    @pytest.mark.parametrize(
        "data_type",
        ["uniqueidentifier", "binary", "varbinary", "image",
         "boolean", "array", "map", "struct", "unknown", ""],
    )
    def test_other_types(self, data_type):
        assert type_category(data_type) == "other"


class TestTypeCategoryTypeEnginePath:
    """isinstance classification — must match the legacy _get_type_category."""

    def test_integer_numeric_float(self):
        assert type_category(sa_types.Integer()) == "numeric"
        assert type_category(sa_types.Numeric()) == "numeric"
        assert type_category(sa_types.Float()) == "numeric"

    def test_money_smallmoney_by_name(self):
        money = type("MONEY", (sa_types.TypeEngine,), {})()
        smallmoney = type("SMALLMONEY", (sa_types.TypeEngine,), {})()
        assert type_category(money) == "numeric"
        assert type_category(smallmoney) == "numeric"

    def test_datetime_date_time(self):
        assert type_category(sa_types.DateTime()) == "datetime"
        assert type_category(sa_types.Date()) == "datetime"
        assert type_category(sa_types.Time()) == "datetime"

    def test_string_text(self):
        assert type_category(sa_types.String()) == "string"
        assert type_category(sa_types.Text()) == "string"

    def test_other(self):
        assert type_category(sa_types.LargeBinary()) == "other"
