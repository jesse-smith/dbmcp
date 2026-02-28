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
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.inference.scoring import ConfidenceScorer
from src.logging_config import get_logger
from src.models.relationship import InferredFK, create_relationship_id

if TYPE_CHECKING:
    from src.inference.value_overlap import ValueOverlapAnalyzer

logger = get_logger(__name__)

# Default timeout for inference operations (10 seconds)
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 10


@dataclass
class ColumnInfo:
    """Column metadata for inference."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_unique: bool
    table_name: str
    schema_name: str


class ForeignKeyInferencer:
    """Infers foreign key relationships from metadata and optionally data values.

    Delegates confidence scoring to ConfidenceScorer.

    T134: Supports configurable timeout with partial results.
    """

    def __init__(
        self,
        engine: Engine,
        threshold: float = 0.50,
        timeout_seconds: float | None = None,
        overlap_threshold: float = 0.30,
    ):
        self.engine = engine
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_INFERENCE_TIMEOUT_SECONDS
        self.overlap_threshold = overlap_threshold
        self._inspector = None
        self._column_cache: dict[str, list[ColumnInfo]] = {}
        self._overlap_analyzer: ValueOverlapAnalyzer | None = None
        self._scorer = ConfidenceScorer()

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

        T134: Supports timeout with partial results.
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
        """
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")

        if max_candidates < 1 or max_candidates > 1000:
            raise ValueError("max_candidates must be between 1 and 1000")

        if include_value_overlap:
            valid_strategies = ["sampling", "full_comparison"]
            if overlap_strategy not in valid_strategies:
                raise ValueError(f"overlap_strategy must be one of: {valid_strategies}")
            if overlap_sample_size < 1 or overlap_sample_size > 10000:
                raise ValueError("overlap_sample_size must be between 1 and 10000")

            if self._overlap_analyzer is None:
                from src.inference.value_overlap import ValueOverlapAnalyzer
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

        all_tables = self._get_all_tables(schema_name)
        inferred = []

        for src_col in source_columns:
            if src_col.is_primary_key:
                continue

            if self.timeout_seconds > 0:
                elapsed = time.time() - start_time
                if elapsed >= self.timeout_seconds:
                    timed_out = True
                    logger.warning(
                        f"FK inference for {schema_name}.{table_name} timed out after {elapsed:.1f}s "
                        f"({tables_analyzed} tables analyzed, {total_evaluated} candidates evaluated)"
                    )
                    break

            for target_schema, target_table in all_tables:
                if target_table == table_name and target_schema == schema_name:
                    continue

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
                    continue

                tables_analyzed += 1
                total_evaluated += 1

                score, factors = self._scorer.calculate_confidence(
                    src_col, target_pk, target_table, include_overlap=False
                )

                if include_value_overlap and score >= (self.threshold * 0.7):
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

                    score, factors = self._scorer.calculate_confidence(
                        src_col, target_pk, target_table,
                        include_overlap=True,
                        overlap_score=overlap_result.overlap_score,
                    )

                if score >= self.threshold:
                    reasoning = self._scorer.generate_reasoning(src_col, target_pk, factors)
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

            if timed_out:
                break

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
                    is_primary_key=col["name"] in pk_columns,
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
        pk_columns = [c for c in columns if c.is_primary_key]
        if len(pk_columns) == 1:
            return pk_columns[0]
        return None

    def clear_cache(self):
        """Clear the column metadata cache."""
        self._column_cache.clear()
        self._inspector = None
