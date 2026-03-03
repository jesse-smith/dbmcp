# Research: Data-Exposure Analysis Tools

**Feature**: 007-analysis-tools | **Date**: 2026-03-03

## R1: Reusable Code from Existing Inference Module

**Decision**: Adapt `ColumnStatsCollector` query patterns; do NOT reuse the class directly.

**Rationale**: The existing `ColumnStatsCollector` (src/inference/column_stats.py) contains proven SQL patterns for:
- Basic stats: `COUNT(DISTINCT)`, null counts, total rows (lines 102-139)
- Numeric stats: min/max/mean/stddev with SQL Server `PERCENTILE_CONT` (lines 175-241)
- DateTime stats: min/max/range with `DATEDIFF` and time component checks (lines 243-332)
- String stats: top values, avg/min/max length (lines 334-408)
- Column existence checks (lines 68-100)

The class itself is tightly coupled to the inference module's structure (separate per-column calls, no batch support). The new `analyze_columns` tool needs to support filtering by column name list or pattern and return results for multiple columns in one call. The SQL patterns are sound and battle-tested, so they should be adapted into the new `src/analysis/column_stats.py` with batch-aware design.

**Alternatives considered**:
- Direct reuse of `ColumnStatsCollector` class → Rejected: would require keeping inference module structure, no batch support
- Writing from scratch → Rejected: existing SQL patterns are proven and handle dialect differences

## R2: Value Overlap Approach for FK Candidates

**Decision**: Adapt the `INTERSECT`-based overlap query from `ValueOverlapAnalyzer._full_comparison`. Replace Jaccard similarity with the spec-required metrics: raw intersection count and percentage of source distinct values found in target.

**Rationale**: The existing overlap code (src/inference/value_overlap.py) uses two strategies:
- `_full_comparison` (lines 228-300): SQL `INTERSECT` for exact counts — this is what we need
- `_sampling_comparison` (lines 302-383): Random sampling with `NEWID()` — not needed for spec requirements

The spec requires exposing raw count + percentage, not Jaccard similarity. The `_full_comparison` approach computes the exact intersection count via SQL, which is efficient for moderate cardinality. For high cardinality, the spec allows indicating overlap was not computed.

**Alternatives considered**:
- Keep sampling strategy → Rejected: spec doesn't require approximate overlap, and the raw count+percentage is simpler
- Pull values into Python → Rejected: SQL-level INTERSECT is more efficient

## R3: PK Candidate Discovery Approach

**Decision**: Combine constraint metadata (from `INFORMATION_SCHEMA` / SQLAlchemy inspector) with structural analysis (uniqueness + non-null + type check) in a single query.

**Rationale**: PK candidates come from two sources:
1. **Constraint-backed**: Columns with PK or UNIQUE constraints — available via `MetadataService.inspector.get_pk_constraint()` and `get_indexes()` (existing code in metadata.py)
2. **Structural**: Columns that are unique, non-null, and match the type set — requires checking `is_nullable`, `is_identity`, and computing `COUNT(DISTINCT)` = `COUNT(*)` (from column stats)

The existing `MetadataService` already queries constraints and indexes. For structural candidates, we need the distinct count and null count from `get_basic_stats`-style queries.

**Alternatives considered**:
- Use only constraint metadata → Rejected: spec explicitly requires structural candidates too
- Query each column individually for uniqueness → Rejected: batch approach is more efficient

## R4: FK Candidate Search Scoping

**Decision**: Default search scope is source column's schema. Target filtering by schema, table list, or LIKE pattern applied as SQL `WHERE` clauses.

**Rationale**: The spec is explicit (FR-007): when no target filters are provided, default to source column's schema. This prevents expensive full-database scans. The scoping parameters (schema, table list, table pattern) are mutually additive filters — all specified filters must match.

The candidate generation flow:
1. Resolve target tables (apply schema/table/pattern filters)
2. For each target table, find candidate columns (all columns, or PK-candidates only)
3. Collect structural metadata for each candidate
4. Optionally compute value overlap
5. Apply limit (default 100)

**Alternatives considered**:
- Compute overlap first to pre-filter → Rejected: overlap is expensive and opt-in
- Return unlimited by default → Rejected: spec requires default limit of 100

## R5: New Data Model Design

**Decision**: Create `src/models/analysis.py` with three dataclasses: `ColumnStatistics`, `PKCandidate`, `FKCandidateData`. Keep them simple, flat, and serializable.

**Rationale**: Separation from schema.py keeps models focused. The spec's "key entities" section defines exactly what each model needs:
- `ColumnStatistics`: distinct_count, total_rows, null_percentage, type_specific_stats (numeric/string/datetime)
- `PKCandidate`: column_name, table_name, is_constraint_backed, constraint_type, properties (unique, non_null, type_match)
- `FKCandidateData`: source/target column/table names, data types, structural metadata, optional overlap_count and overlap_percentage

**Alternatives considered**:
- Add fields to existing Column model → Rejected: Column model is for schema metadata, not analysis results
- Use dicts instead of dataclasses → Rejected: constitution requires typed data structures

## R6: Removal Scope and Dependency Graph

**Decision**: Remove in dependency order: tools → modules → models. Verify no remaining imports after each step.

**Rationale**: The removal dependency graph:
1. **MCP tools** (leaf nodes, no dependents):
   - `src/mcp_server/doc_tools.py` (entire file) — imports from cache/
   - `infer_relationships` in schema_tools.py — imports from inference/
   - `analyze_column` in query_tools.py — imports from inference/
2. **Modules** (depended on only by removed tools):
   - `src/inference/` (entire directory) — 6 files
   - `src/cache/` (entire directory) — 3 files
3. **Models** (depended on by removed modules):
   - `InferredPurpose` enum, `inferred_purpose`/`inferred_confidence` fields on Column
   - `InferredFK`, `InferenceFactors` dataclasses
   - `DocumentationCache` dataclass
   - `RelationshipType.INFERRED` enum value (if no longer used)
4. **Tests** referencing removed code

The `Relationship` base class and `DeclaredFK` remain unchanged per FR-012. `RelationshipType` enum keeps `DECLARED` — `INFERRED` can be removed since `InferredFK` is removed.

## R7: Stat Dataclass Adaptation

**Decision**: Redefine stat dataclasses in `src/models/analysis.py`, removing inference-specific fields.

**Rationale**: The existing stat dataclasses (`NumericStats`, `DateTimeStats`, `StringStats`) in `src/inference/column_stats.py` contain some inference-oriented fields:
- `NumericStats.is_integer` — this is interpretive (decides if values are integers). Remove.
- `DateTimeStats.business_hours_percentage` — this is interpretive. Remove.
- `DateTimeStats.has_time_component` — borderline, but it's a raw boolean check. Keep as structural metadata.
- `StringStats.all_uppercase`, `StringStats.contains_numbers` — interpretive pattern labels. Remove.
- `StringStats.top_values` — this is "sample patterns" per the spec. Rename to `sample_values`.

The spec says: expose raw statistics, no interpretive labels. Keep min/max/mean/stddev/length stats, remove pattern-based booleans.
