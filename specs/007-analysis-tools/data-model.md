# Data Model: Data-Exposure Analysis Tools

**Feature**: 007-analysis-tools | **Date**: 2026-03-03

## New Models (src/models/analysis.py)

### NumericStats

Per-column statistics for numeric types.

| Field | Type | Description |
|-------|------|-------------|
| min_value | `float \| None` | Minimum value |
| max_value | `float \| None` | Maximum value |
| mean_value | `float \| None` | Arithmetic mean |
| std_dev | `float \| None` | Standard deviation |

### DateTimeStats

Per-column statistics for date/time types.

| Field | Type | Description |
|-------|------|-------------|
| min_date | `datetime \| None` | Earliest value |
| max_date | `datetime \| None` | Latest value |
| date_range_days | `int \| None` | Days between min and max |
| has_time_component | `bool` | Whether any non-midnight times exist |

### StringStats

Per-column statistics for string types.

| Field | Type | Description |
|-------|------|-------------|
| min_length | `int \| None` | Shortest string length |
| max_length | `int \| None` | Longest string length |
| avg_length | `float \| None` | Average string length |
| sample_values | `list[tuple[str, int]]` | Top N most frequent (value, frequency) pairs, where N defaults to 10 and is configurable via the `sample_size` parameter |

### ColumnStatistics

Complete statistical profile for a single column.

| Field | Type | Description |
|-------|------|-------------|
| column_name | `str` | Column name |
| table_name | `str` | Parent table name |
| schema_name | `str` | Parent schema name |
| data_type | `str` | SQL data type string |
| total_rows | `int` | Total row count in table |
| distinct_count | `int` | Number of distinct non-null values |
| null_count | `int` | Number of null values |
| null_percentage | `float` | Percentage of null values (0.0-100.0) |
| numeric_stats | `NumericStats \| None` | Present for numeric columns |
| datetime_stats | `DateTimeStats \| None` | Present for datetime columns |
| string_stats | `StringStats \| None` | Present for string columns |

**Serialization**: `to_dict()` method returns JSON-safe dict. Type-specific stats only included when not None.

### PKCandidate

A column meeting primary key candidacy criteria.

| Field | Type | Description |
|-------|------|-------------|
| column_name | `str` | Column name |
| data_type | `str` | SQL data type string |
| is_constraint_backed | `bool` | True if PK or UNIQUE constraint exists |
| constraint_type | `str \| None` | "PRIMARY KEY" or "UNIQUE" if constraint-backed, None otherwise |
| is_unique | `bool` | Whether all non-null values are unique |
| is_non_null | `bool` | Whether column has zero nulls |
| is_pk_type | `bool` | Whether type matches the configured PK type set |

**Note**: Table and schema are not per-candidate fields — PK discovery is scoped to a single table, so these are top-level response metadata only.

**Serialization**: `to_dict()` method.

### FKCandidateData

Raw data for a single source-to-target FK candidate pair.

| Field | Type | Description |
|-------|------|-------------|
| source_column | `str` | Source column name |
| source_table | `str` | Source table name |
| source_schema | `str` | Source schema name |
| source_data_type | `str` | Source column data type |
| target_column | `str` | Target column name |
| target_table | `str` | Target table name |
| target_schema | `str` | Target schema name |
| target_data_type | `str` | Target column data type |
| target_is_primary_key | `bool` | Target has PK constraint |
| target_is_unique | `bool` | Target has UNIQUE constraint or unique values |
| target_is_nullable | `bool` | Target allows nulls |
| target_has_index | `bool` | Target is indexed |
| overlap_count | `int \| None` | Raw count of source distinct values found in target (when overlap enabled) |
| overlap_percentage | `float \| None` | Percentage of source distinct values found in target (when overlap enabled) |

**Serialization**: `to_dict()` method. Overlap fields omitted from dict when None.

### FKCandidateResult

Wrapper for FK candidate search results.

| Field | Type | Description |
|-------|------|-------------|
| candidates | `list[FKCandidateData]` | List of candidate pairs |
| total_found | `int` | Total candidates before limit applied |
| was_limited | `bool` | True if results were truncated by limit |
| search_scope | `str` | Description of search scope applied |

## Modified Models

### Column (src/models/schema.py)

**Fields removed**:
- `inferred_purpose: InferredPurpose | None` — interpretive label
- `inferred_confidence: float | None` — confidence score
- `distinct_count: int | None` — moved to ColumnStatistics (on-demand, not stored on Column)
- `null_percentage: float | None` — moved to ColumnStatistics

**Fields retained**: All other fields (column_id, table_id, column_name, ordinal_position, data_type, max_length, is_nullable, default_value, is_identity, is_computed, is_primary_key, is_foreign_key)

### Enums removed from schema.py

- `InferredPurpose` — entire enum deleted

### Models removed from schema.py

- `DocumentationCache` — entire dataclass deleted

### Models removed from relationship.py

- `InferenceFactors` — entire dataclass deleted
- `InferredFK` — entire dataclass deleted

### Enum values removed from relationship.py

- `RelationshipType.INFERRED` — removed (only `DECLARED` remains)

### Models retained unchanged

- `DeclaredFK` (FR-012)
- `Relationship` (base class, still used by `DeclaredFK`)
- All other schema.py models (Connection, Schema, Table, Index, Query, SampleData, ValidationResult, DenialReason)

## Entity Relationships

```
ColumnStatistics ─── has one of ──┬── NumericStats
                                  ├── DateTimeStats
                                  └── StringStats

PKCandidate (standalone, no FK to other models)

FKCandidateResult ─── contains ──── FKCandidateData[]

find_fk_candidates ─── uses ──── find_pk_candidates (when PK filter enabled)
```

## Validation Rules

- `ColumnStatistics.null_percentage`: 0.0 to 100.0 inclusive
- `ColumnStatistics.distinct_count`: >= 0
- `ColumnStatistics.total_rows`: >= 0
- `FKCandidateData.overlap_percentage`: 0.0 to 100.0 inclusive (when present)
- `FKCandidateData.overlap_count`: >= 0 (when present)
- `FKCandidateResult.total_found`: >= len(candidates)
