"""Purpose pattern matching for column analysis.

Categorizes column data types and infers column purpose based on
naming conventions, value distributions, and statistical patterns.
"""

import re
from enum import StrEnum

from src.inference.column_stats import NumericStats, StringStats
from src.models.schema import InferredPurpose


class ColumnCategory(StrEnum):
    """Categories of column data types for analysis."""

    NUMERIC = "numeric"
    STRING = "string"
    DATETIME = "datetime"
    BINARY = "binary"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


# Type compatibility groups for categorization
NUMERIC_TYPES = {
    "int", "bigint", "smallint", "tinyint", "bit",
    "decimal", "numeric", "float", "real", "money", "smallmoney",
    "integer",  # SQLite
}

DATETIME_TYPES = {
    "date", "datetime", "datetime2", "datetimeoffset",
    "smalldatetime", "time", "timestamp",
}

STRING_TYPES = {
    "char", "varchar", "nchar", "nvarchar", "text", "ntext",
}

BINARY_TYPES = {
    "binary", "varbinary", "image", "blob",
}

# Thresholds for enum detection
ENUM_MAX_DISTINCT = 50
ENUM_MAX_PERCENTAGE = 10.0


def categorize_type(data_type: str) -> ColumnCategory:
    """Categorize SQL data type into a category."""
    base_type = data_type.lower().split("(")[0].strip()

    if base_type in NUMERIC_TYPES:
        return ColumnCategory.NUMERIC
    elif base_type in DATETIME_TYPES:
        return ColumnCategory.DATETIME
    elif base_type in STRING_TYPES:
        return ColumnCategory.STRING
    elif base_type in BINARY_TYPES:
        return ColumnCategory.BINARY
    elif base_type == "bit":
        return ColumnCategory.BOOLEAN
    else:
        return ColumnCategory.UNKNOWN


def is_enum(
    distinct_count: int,
    total_rows: int,
    category: ColumnCategory | None = None,
) -> bool:
    """Detect if column appears to be an enumeration."""
    if total_rows == 0:
        return False

    if category in (ColumnCategory.DATETIME, ColumnCategory.BINARY):
        return False

    if total_rows < 100:
        return distinct_count <= min(20, ENUM_MAX_DISTINCT)

    percentage = (distinct_count / total_rows) * 100
    return distinct_count <= ENUM_MAX_DISTINCT and percentage <= ENUM_MAX_PERCENTAGE


def infer_purpose(
    column_name: str,
    data_type: str,
    category: ColumnCategory,
    distinct_count: int,
    null_percentage: float,
    total_rows: int,
    is_enum_flag: bool,
    numeric_stats: NumericStats | None,
    datetime_stats=None,
    string_stats: StringStats | None = None,
) -> tuple[InferredPurpose, float, str]:
    """Infer the purpose of a column based on analysis.

    Returns:
        Tuple of (purpose, confidence, reasoning)
    """
    reasoning_parts = []
    purpose = InferredPurpose.UNKNOWN
    confidence = 0.0

    name_lower = column_name.lower()
    name_normalized = re.sub(r'[_\-\s]', '', name_lower)

    if _is_likely_id(name_lower, name_normalized, category, numeric_stats, distinct_count, total_rows):
        purpose = InferredPurpose.ID
        confidence = 0.85
        reasoning_parts.append("Name pattern suggests identifier")
        if numeric_stats and numeric_stats.is_integer:
            reasoning_parts.append("Integer values")
            confidence += 0.05
        if distinct_count == total_rows:
            reasoning_parts.append("All values unique")
            confidence += 0.05

    elif _is_likely_flag(name_lower, name_normalized, category, distinct_count, string_stats):
        purpose = InferredPurpose.FLAG
        confidence = 0.85
        reasoning_parts.append("Name pattern suggests boolean flag")
        if distinct_count <= 2:
            reasoning_parts.append(f"Only {distinct_count} distinct values")
            confidence += 0.10

    elif _is_likely_status(name_lower, name_normalized, is_enum_flag, distinct_count, string_stats):
        purpose = InferredPurpose.STATUS
        confidence = 0.80
        reasoning_parts.append("Name pattern suggests status field")
        if is_enum_flag:
            reasoning_parts.append(f"Enumeration with {distinct_count} values")
            confidence += 0.10

    elif is_enum_flag and category == ColumnCategory.STRING:
        purpose = InferredPurpose.ENUM
        confidence = 0.75
        reasoning_parts.append(f"Low cardinality ({distinct_count} values)")
        if string_stats and string_stats.all_uppercase:
            reasoning_parts.append("All uppercase values (code-like)")
            confidence += 0.10

    elif _is_likely_amount(name_lower, name_normalized, category, numeric_stats):
        purpose = InferredPurpose.AMOUNT
        confidence = 0.80
        reasoning_parts.append("Name pattern suggests monetary amount")
        if numeric_stats:
            reasoning_parts.append(f"Range: {numeric_stats.min_value} to {numeric_stats.max_value}")

    elif _is_likely_quantity(name_lower, name_normalized, category, numeric_stats):
        purpose = InferredPurpose.QUANTITY
        confidence = 0.75
        reasoning_parts.append("Name pattern suggests quantity/count")
        if numeric_stats and numeric_stats.is_integer:
            reasoning_parts.append("Integer values")
            confidence += 0.10

    elif _is_likely_percentage(name_lower, name_normalized, category, numeric_stats):
        purpose = InferredPurpose.PERCENTAGE
        confidence = 0.80
        reasoning_parts.append("Name pattern suggests percentage")
        if numeric_stats and numeric_stats.min_value is not None and numeric_stats.max_value is not None:
            if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 100:
                reasoning_parts.append("Values in 0-100 range")
                confidence += 0.10

    elif category == ColumnCategory.DATETIME:
        purpose = InferredPurpose.TIMESTAMP
        confidence = 0.75
        reasoning_parts.append("DateTime data type")
        if datetime_stats and datetime_stats.has_time_component:
            reasoning_parts.append("Contains time component")
            confidence += 0.10
        if "created" in name_lower or "modified" in name_lower or "updated" in name_lower:
            reasoning_parts.append("Name suggests audit timestamp")
            confidence += 0.10

    else:
        purpose = InferredPurpose.UNKNOWN
        confidence = 0.50
        reasoning_parts.append("No strong pattern detected")

    confidence = min(confidence, 1.0)
    return purpose, confidence, "; ".join(reasoning_parts)


def _is_likely_id(
    name_lower: str,
    name_normalized: str,
    category: ColumnCategory,
    numeric_stats: NumericStats | None,
    distinct_count: int,
    total_rows: int,
) -> bool:
    """Check if column is likely an identifier."""
    id_suffixes = ["_id", "id", "_key", "key", "_no", "no", "_num", "num"]

    if any(name_normalized.endswith(suffix.replace("_", "")) for suffix in id_suffixes):
        return True
    if name_lower == "id" or name_normalized == "id":
        return True

    non_id_patterns = [
        "amt", "amount", "price", "cost", "total", "sum", "balance",
        "fee", "charge", "payment", "salary", "wage",
        "qty", "quantity", "count", "cnt", "units", "items",
        "pct", "percent", "percentage", "rate", "ratio",
    ]
    has_non_id_pattern = any(pattern in name_lower for pattern in non_id_patterns)

    if (
        category == ColumnCategory.NUMERIC
        and numeric_stats
        and numeric_stats.is_integer
        and distinct_count == total_rows
        and total_rows > 0
        and not has_non_id_pattern
    ):
        return True

    return False


def _is_likely_flag(
    name_lower: str,
    name_normalized: str,
    category: ColumnCategory,
    distinct_count: int,
    string_stats: StringStats | None,
) -> bool:
    """Check if column is likely a boolean flag."""
    flag_patterns = ["flag", "flg", "is_", "has_", "can_", "should_", "active", "enabled", "disabled"]

    for pattern in flag_patterns:
        if pattern in name_lower:
            return True

    if distinct_count <= 2:
        if string_stats and string_stats.top_values:
            values = [v[0].lower() for v in string_stats.top_values]
            binary_pairs = [
                {"y", "n"}, {"yes", "no"}, {"true", "false"},
                {"1", "0"}, {"t", "f"}, {"on", "off"},
                {"active", "inactive"}, {"enabled", "disabled"}
            ]
            for pair in binary_pairs:
                if set(values).issubset(pair):
                    return True

    return False


def _is_likely_status(
    name_lower: str,
    name_normalized: str,
    is_enum_flag: bool,
    distinct_count: int,
    string_stats: StringStats | None,
) -> bool:
    """Check if column is likely a status field."""
    status_patterns = ["status", "state", "stage", "phase", "step"]

    for pattern in status_patterns:
        if pattern in name_lower:
            return True

    if is_enum_flag and string_stats and string_stats.top_values:
        values = [v[0].lower() for v in string_stats.top_values]
        status_values = {"pending", "active", "inactive", "complete", "completed",
                       "cancelled", "canceled", "draft", "approved", "rejected",
                       "new", "open", "closed", "in_progress", "inprogress"}
        if any(v in status_values for v in values):
            return True

    return False


def _is_likely_amount(
    name_lower: str,
    name_normalized: str,
    category: ColumnCategory,
    numeric_stats: NumericStats | None,
) -> bool:
    """Check if column is likely a monetary amount."""
    if category != ColumnCategory.NUMERIC:
        return False

    amount_patterns = ["amt", "amount", "price", "cost", "total", "sum",
                     "balance", "fee", "charge", "payment", "salary", "wage"]

    for pattern in amount_patterns:
        if pattern in name_lower:
            return True

    return False


def _is_likely_quantity(
    name_lower: str,
    name_normalized: str,
    category: ColumnCategory,
    numeric_stats: NumericStats | None,
) -> bool:
    """Check if column is likely a quantity/count."""
    if category != ColumnCategory.NUMERIC:
        return False

    qty_patterns = ["qty", "quantity", "count", "cnt", "num", "units", "items"]

    for pattern in qty_patterns:
        if pattern in name_lower:
            return True

    if numeric_stats and numeric_stats.is_integer:
        if numeric_stats.min_value is not None and numeric_stats.min_value >= 0:
            return True

    return False


def _is_likely_percentage(
    name_lower: str,
    name_normalized: str,
    category: ColumnCategory,
    numeric_stats: NumericStats | None,
) -> bool:
    """Check if column is likely a percentage."""
    if category != ColumnCategory.NUMERIC:
        return False

    pct_patterns = ["pct", "percent", "percentage", "rate", "ratio"]

    for pattern in pct_patterns:
        if pattern in name_lower:
            return True

    if numeric_stats:
        if numeric_stats.min_value is not None and numeric_stats.max_value is not None:
            if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 100:
                return True
            if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 1:
                return True

    return False
