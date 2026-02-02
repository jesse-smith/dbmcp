"""Foreign key inference algorithm.

This module implements FK inference using weighted scoring:

Phase 1 (metadata-only):
- Name similarity (40% weight)
- Type compatibility (15% weight, veto if incompatible)
- Structural hints (45% weight)

Phase 2 (with value overlap - T142):
- Name similarity (32% weight - reduced from 40%)
- Type compatibility (12% weight - reduced from 15%)
- Structural hints (36% weight - reduced from 45%)
- Value overlap (20% weight - new factor)

Target accuracy: 75-80% (Phase 1), 85-90% (Phase 2).

T134: Supports configurable timeout with partial results.
"""

import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.relationship import InferenceFactors, InferredFK, create_relationship_id

if TYPE_CHECKING:
    from src.inference.value_overlap import ValueOverlapAnalyzer

logger = get_logger(__name__)

# Default timeout for inference operations (10 seconds)
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 10

# Weight configuration for Phase 1 (metadata-only)
PHASE1_WEIGHTS = {
    "name": 0.40,
    "type": 0.15,
    "structural": 0.45,
}

# Weight configuration for Phase 2 (with value overlap)
# Reduces other factors to make room for 20% overlap weight
PHASE2_WEIGHTS = {
    "name": 0.32,        # 40% * 0.80 = 32%
    "type": 0.12,        # 15% * 0.80 = 12%
    "structural": 0.36,  # 45% * 0.80 = 36%
    "overlap": 0.20,     # New factor: 20%
}

# SQL Server compatible type groups
TYPE_GROUPS = {
    "NUMERIC": ["int", "bigint", "smallint", "tinyint", "numeric", "decimal", "float", "real", "money"],
    "STRING": ["varchar", "nvarchar", "char", "nchar", "text", "ntext"],
    "GUID": ["uniqueidentifier"],
    "DATE": ["datetime", "datetime2", "date", "time", "datetimeoffset", "smalldatetime"],
    "BINARY": ["binary", "varbinary", "image"],
}

# Common ID column suffixes (normalized)
ID_SUFFIXES = ["id", "key", "code", "num", "number", "no"]


@dataclass
class ColumnInfo:
    """Column metadata for inference."""

    name: str
    data_type: str
    is_nullable: bool
    is_pk: bool
    is_unique: bool
    table_name: str
    schema_name: str


class ForeignKeyInferencer:
    """Infers foreign key relationships from metadata and optionally data values.

    Phase 1 (metadata-only) uses three-factor weighted scoring:
    - Name similarity (40%): Column name pattern matching
    - Type compatibility (15%): Data type group matching
    - Structural hints (45%): PK, nullable, unique index indicators

    Phase 2 (with value overlap - T142) adds a fourth factor:
    - Value overlap (20%): Actual data value matching via Jaccard similarity
    - Other factors reduced proportionally to 80% of original weights

    T134: Supports configurable timeout with partial results.

    Attributes:
        engine: SQLAlchemy database engine
        threshold: Minimum confidence score to return (default: 0.50)
        timeout_seconds: Maximum time for inference before returning partial results
        overlap_threshold: Minimum overlap score to consider valid (default: 0.30)
    """

    def __init__(
        self,
        engine: Engine,
        threshold: float = 0.50,
        timeout_seconds: float | None = None,
        overlap_threshold: float = 0.30,
    ):
        """Initialize the inferencer.

        Args:
            engine: SQLAlchemy engine for database access
            threshold: Minimum confidence threshold (0.0-1.0)
            timeout_seconds: Maximum inference time (None = default 10s, 0 = no timeout)
            overlap_threshold: Minimum value overlap score (0.0-1.0, default: 0.30)
        """
        self.engine = engine
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_INFERENCE_TIMEOUT_SECONDS
        self.overlap_threshold = overlap_threshold
        self._inspector = None
        self._column_cache: dict[str, list[ColumnInfo]] = {}
        self._overlap_analyzer: ValueOverlapAnalyzer | None = None

    @property
    def inspector(self):
        """Lazily create inspector."""
        if self._inspector is None:
            self._inspector = inspect(self.engine)
        return self._inspector

    def infer_relationships(
        self,
        table_name: str,
        schema_name: str = "dbo",
        max_candidates: int = 20,
        include_value_overlap: bool = False,
        overlap_strategy: str = "sampling",
        overlap_sample_size: int = 1000,
    ) -> tuple[list[InferredFK], dict]:
        """Infer foreign key relationships for a table.

        T134: Supports timeout with partial results. If inference exceeds
        timeout_seconds, returns partial results with timed_out=True in metadata.

        T142: Supports value overlap analysis for improved accuracy.

        Args:
            table_name: Source table to analyze
            schema_name: Schema containing the table
            max_candidates: Maximum candidates to return
            include_value_overlap: If True, use value overlap analysis (Phase 2)
            overlap_strategy: Strategy for overlap analysis - 'sampling' or 'full_comparison'
            overlap_sample_size: Sample size for sampling strategy (default: 1000)

        Returns:
            Tuple of (inferred relationships, analysis metadata)
            Metadata includes: analysis_time_ms, total_candidates_evaluated, timed_out, tables_analyzed

        Raises:
            ValueError: If parameters are invalid
        """
        # Parameter validation
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")

        if max_candidates < 1 or max_candidates > 1000:
            raise ValueError("max_candidates must be between 1 and 1000")

        # Validate overlap parameters if enabled
        if include_value_overlap:
            valid_strategies = ["sampling", "full_comparison"]
            if overlap_strategy not in valid_strategies:
                raise ValueError(f"overlap_strategy must be one of: {valid_strategies}")
            if overlap_sample_size < 1 or overlap_sample_size > 10000:
                raise ValueError("overlap_sample_size must be between 1 and 10000")

            # Lazy initialization of overlap analyzer
            if self._overlap_analyzer is None:
                from src.inference.value_overlap import OverlapStrategy, ValueOverlapAnalyzer
                self._overlap_analyzer = ValueOverlapAnalyzer(
                    engine=self.engine,
                    timeout_seconds=self.timeout_seconds,
                    default_sample_size=overlap_sample_size,
                )

        start_time = time.time()
        total_evaluated = 0
        tables_analyzed = 0
        timed_out = False
        overlap_analyses = 0

        # Get source table columns
        source_columns = self._get_columns(table_name, schema_name)
        if not source_columns:
            logger.warning(f"No columns found for {schema_name}.{table_name}")
            return [], {
                "analysis_time_ms": 0,
                "total_candidates_evaluated": 0,
                "timed_out": False,
                "tables_analyzed": 0,
                "overlap_analyses": 0,
                "include_value_overlap": include_value_overlap,
            }

        # Get all potential target tables
        all_tables = self._get_all_tables(schema_name)
        inferred = []

        # For each non-PK column in source table
        for src_col in source_columns:
            if src_col.is_pk:
                continue  # PKs are typically not FKs

            # T134: Check timeout before each column iteration
            if self.timeout_seconds > 0:
                elapsed = time.time() - start_time
                if elapsed >= self.timeout_seconds:
                    timed_out = True
                    logger.warning(
                        f"FK inference for {schema_name}.{table_name} timed out after {elapsed:.1f}s "
                        f"({tables_analyzed} tables analyzed, {total_evaluated} candidates evaluated)"
                    )
                    break

            # Check against each potential target table
            for target_schema, target_table in all_tables:
                if target_table == table_name and target_schema == schema_name:
                    continue  # Skip self-references for now

                # T134: Periodic timeout check during inner loop
                if self.timeout_seconds > 0 and total_evaluated % 50 == 0:
                    elapsed = time.time() - start_time
                    if elapsed >= self.timeout_seconds:
                        timed_out = True
                        logger.warning(
                            f"FK inference for {schema_name}.{table_name} timed out after {elapsed:.1f}s "
                            f"({tables_analyzed} tables analyzed, {total_evaluated} candidates evaluated)"
                        )
                        break

                target_columns = self._get_columns(target_table, target_schema)
                target_pk = self._get_primary_key_column(target_columns)

                if not target_pk:
                    continue  # Can't FK to table without PK

                tables_analyzed += 1
                total_evaluated += 1

                # Score this potential relationship (metadata-only first pass)
                score, factors = self._calculate_confidence(
                    src_col, target_pk, target_table, include_overlap=False
                )

                # If include_value_overlap and passes initial threshold, add overlap analysis
                if include_value_overlap and score >= (self.threshold * 0.7):
                    # Only analyze overlap for candidates that have reasonable metadata scores
                    from src.inference.value_overlap import OverlapStrategy
                    strategy = (
                        OverlapStrategy.FULL_COMPARISON
                        if overlap_strategy == "full_comparison"
                        else OverlapStrategy.SAMPLING
                    )

                    overlap_result = self._overlap_analyzer.calculate_overlap(
                        source_table=table_name,
                        source_column=src_col.name,
                        source_schema=schema_name,
                        target_table=target_table,
                        target_column=target_pk.name,
                        target_schema=target_schema,
                        strategy=strategy,
                        sample_size=overlap_sample_size,
                    )
                    overlap_analyses += 1

                    # Recalculate score with overlap factor
                    score, factors = self._calculate_confidence(
                        src_col, target_pk, target_table,
                        include_overlap=True,
                        overlap_score=overlap_result.overlap_score,
                    )

                if score >= self.threshold:
                    reasoning = self._generate_reasoning(src_col, target_pk, factors)
                    relationship_id = create_relationship_id(
                        f"{schema_name}.{table_name}",
                        src_col.name,
                        f"{target_schema}.{target_table}",
                        target_pk.name,
                    )

                    inferred.append(InferredFK(
                        relationship_id=relationship_id,
                        source_table_id=f"{schema_name}.{table_name}",
                        source_column=src_col.name,
                        target_table_id=f"{target_schema}.{target_table}",
                        target_column=target_pk.name,
                        confidence_score=round(score, 3),
                        reasoning=reasoning,
                        inference_factors=factors,
                    ))

            # Break outer loop if timed out
            if timed_out:
                break

        # Sort by confidence descending and limit
        inferred.sort(key=lambda x: x.confidence_score, reverse=True)
        inferred = inferred[:max_candidates]

        elapsed_ms = int((time.time() - start_time) * 1000)
        if timed_out:
            logger.info(f"FK inference for {schema_name}.{table_name}: {len(inferred)} found (PARTIAL) in {elapsed_ms}ms")
        else:
            logger.debug(f"FK inference for {schema_name}.{table_name}: {len(inferred)} found in {elapsed_ms}ms")

        return inferred, {
            "analysis_time_ms": elapsed_ms,
            "total_candidates_evaluated": total_evaluated,
            "timed_out": timed_out,
            "tables_analyzed": tables_analyzed,
            "overlap_analyses": overlap_analyses,
            "include_value_overlap": include_value_overlap,
        }

    def _get_columns(self, table_name: str, schema_name: str) -> list[ColumnInfo]:
        """Get column metadata for a table (cached)."""
        cache_key = f"{schema_name}.{table_name}"
        if cache_key in self._column_cache:
            return self._column_cache[cache_key]

        columns = []
        try:
            inspector_columns = self.inspector.get_columns(table_name, schema=schema_name)
            pk_constraint = self.inspector.get_pk_constraint(table_name, schema=schema_name)
            pk_columns = set(pk_constraint.get("constrained_columns", []))

            # Get unique indexes
            indexes = self.inspector.get_indexes(table_name, schema=schema_name)
            unique_columns = set()
            for idx in indexes:
                if idx.get("unique") and len(idx.get("column_names", [])) == 1:
                    unique_columns.add(idx["column_names"][0])

            for col in inspector_columns:
                columns.append(ColumnInfo(
                    name=col["name"],
                    data_type=str(col["type"]).lower(),
                    is_nullable=col.get("nullable", True),
                    is_pk=col["name"] in pk_columns,
                    is_unique=col["name"] in unique_columns or col["name"] in pk_columns,
                    table_name=table_name,
                    schema_name=schema_name,
                ))

        except Exception as e:
            logger.warning(f"Error getting columns for {schema_name}.{table_name}: {e}")

        self._column_cache[cache_key] = columns
        return columns

    def _get_all_tables(self, default_schema: str) -> list[tuple[str, str]]:
        """Get all tables in the database as (schema, table) tuples."""
        tables = []
        try:
            for schema in self.inspector.get_schema_names():
                if schema in ("sys", "INFORMATION_SCHEMA", "guest"):
                    continue
                for table in self.inspector.get_table_names(schema=schema):
                    tables.append((schema, table))
        except Exception as e:
            logger.warning(f"Error listing tables: {e}")
        return tables

    def _get_primary_key_column(self, columns: list[ColumnInfo]) -> ColumnInfo | None:
        """Get the primary key column (single-column PKs only for now)."""
        pk_columns = [c for c in columns if c.is_pk]
        if len(pk_columns) == 1:
            return pk_columns[0]
        return None

    def _calculate_confidence(
        self,
        src_col: ColumnInfo,
        tgt_col: ColumnInfo,
        tgt_table: str,
        include_overlap: bool = False,
        overlap_score: float | None = None,
    ) -> tuple[float, InferenceFactors]:
        """Calculate confidence score using weighted scoring.

        Phase 1 (include_overlap=False): Three-factor scoring
        Phase 2 (include_overlap=True): Four-factor scoring with value overlap

        Args:
            src_col: Source column info
            tgt_col: Target column info
            tgt_table: Target table name
            include_overlap: Whether to include value overlap in scoring
            overlap_score: Value overlap score (0.0-1.0), required if include_overlap=True

        Returns:
            Tuple of (score, factors)
        """
        # Factor 1: Type compatibility (veto if incompatible)
        type_compatible = self._check_type_compatibility(src_col.data_type, tgt_col.data_type)
        if not type_compatible:
            return 0.0, InferenceFactors(name_similarity=0, type_compatible=False)

        # Factor 2: Name similarity
        name_score = self._calculate_name_similarity(src_col.name, tgt_col.name, tgt_table)

        # Factor 3: Structural hints
        structural_score, hints = self._calculate_structural_score(src_col, tgt_col)

        # Select weights based on whether overlap is included
        if include_overlap and overlap_score is not None:
            # Phase 2 weights (adjusted to make room for overlap)
            weights = PHASE2_WEIGHTS
            final_score = (
                (name_score * weights["name"]) +
                (1.0 * weights["type"]) +  # Type is binary
                (structural_score * weights["structural"]) +
                (overlap_score * weights["overlap"])
            )

            factors = InferenceFactors(
                name_similarity=round(name_score, 3),
                type_compatible=True,
                structural_hints=hints,
                value_overlap=round(overlap_score, 3),
            )
        else:
            # Phase 1 weights (original)
            weights = PHASE1_WEIGHTS
            final_score = (
                (name_score * weights["name"]) +
                (1.0 * weights["type"]) +
                (structural_score * weights["structural"])
            )

            factors = InferenceFactors(
                name_similarity=round(name_score, 3),
                type_compatible=True,
                structural_hints=hints,
            )

        return final_score, factors

    def _check_type_compatibility(self, src_type: str, tgt_type: str) -> bool:
        """Check if types are compatible for FK relationship."""
        src_type = src_type.lower()
        tgt_type = tgt_type.lower()

        # Exact match
        if src_type == tgt_type:
            return True

        # Check if both in same type group
        for group_types in TYPE_GROUPS.values():
            src_in = any(t in src_type for t in group_types)
            tgt_in = any(t in tgt_type for t in group_types)
            if src_in and tgt_in:
                return True

        return False

    def _calculate_name_similarity(self, src_name: str, tgt_name: str, tgt_table: str) -> float:
        """Calculate name similarity score (0.0-1.0)."""
        src_norm = self._normalize_name(src_name)
        tgt_norm = self._normalize_name(tgt_name)

        # Pattern 1: Exact match
        if src_norm == tgt_norm:
            return 1.0

        # Pattern 2: Table prefix pattern (e.g., CustomerID -> Customers.ID)
        tgt_table_norm = self._normalize_name(tgt_table).rstrip("s")  # Remove plural
        if src_norm.startswith(tgt_table_norm):
            suffix = src_norm[len(tgt_table_norm):]
            if suffix in ID_SUFFIXES or suffix == "":
                return 0.90

        # Pattern 3: Source has table name embedded
        for suffix in ID_SUFFIXES:
            if src_norm.endswith(suffix):
                src_base = src_norm[:-len(suffix)]
                if src_base and (src_base in tgt_table_norm or tgt_table_norm in src_base):
                    return 0.85

        # Pattern 4: String similarity using SequenceMatcher
        similarity = SequenceMatcher(None, src_norm, tgt_norm).ratio()

        if similarity > 0.85:
            return 0.80
        elif similarity > 0.70:
            return 0.55
        elif similarity > 0.60:
            return 0.30

        return 0.0

    def _normalize_name(self, name: str) -> str:
        """Normalize column/table name for comparison."""
        return name.lower().replace("_", "").replace("-", "")

    def _calculate_structural_score(self, src_col: ColumnInfo, tgt_col: ColumnInfo) -> tuple[float, list[str]]:
        """Calculate structural hints score (0.0-1.0)."""
        score = 0.5  # Baseline
        hints = []

        # FK columns are typically nullable (+0.2)
        if src_col.is_nullable:
            score += 0.2
            hints.append("source_nullable")
        else:
            score -= 0.1

        # Target should be PK (+0.3)
        if tgt_col.is_pk:
            score += 0.3
            hints.append("target_is_pk")
        elif tgt_col.is_unique:
            score += 0.15
            hints.append("target_unique_index")

        return min(score, 1.0), hints

    def _generate_reasoning(self, src_col: ColumnInfo, tgt_col: ColumnInfo, factors: InferenceFactors) -> str:
        """Generate human-readable explanation for the inference."""
        parts = []

        # Name similarity description
        if factors.name_similarity >= 0.90:
            parts.append(f"Exact/strong name match ({factors.name_similarity:.0%})")
        elif factors.name_similarity >= 0.70:
            parts.append(f"High name similarity ({factors.name_similarity:.0%})")
        elif factors.name_similarity >= 0.50:
            parts.append(f"Moderate name similarity ({factors.name_similarity:.0%})")

        # Type compatibility
        if factors.type_compatible:
            parts.append("type compatible")

        # Structural hints
        if factors.structural_hints:
            parts.append(" + ".join(factors.structural_hints))

        # Value overlap (Phase 2)
        if factors.value_overlap is not None:
            if factors.value_overlap >= 0.80:
                parts.append(f"strong value overlap ({factors.value_overlap:.0%})")
            elif factors.value_overlap >= 0.50:
                parts.append(f"moderate value overlap ({factors.value_overlap:.0%})")
            elif factors.value_overlap >= 0.30:
                parts.append(f"weak value overlap ({factors.value_overlap:.0%})")

        return " + ".join(parts) if parts else "Pattern match"

    def clear_cache(self):
        """Clear the column metadata cache."""
        self._column_cache.clear()
        self._inspector = None
