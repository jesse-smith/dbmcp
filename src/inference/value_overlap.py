"""Value overlap analysis for foreign key inference.

This module implements Phase 2 FK inference enhancement using actual data
value comparison between potential FK columns.

Two strategies are supported:
- full_comparison: Hash all distinct values, compute Jaccard similarity
- sampling: Random sample N values (default 1000) for faster analysis

Target: Improve inference accuracy from 75-80% (Phase 1) to 85-90% (Phase 2).

Performance target: Overlap analysis must not exceed 10s per table pair.
"""

import time
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.metrics import get_metrics

logger = get_logger(__name__)

# Default timeout for overlap analysis per column pair
DEFAULT_OVERLAP_TIMEOUT_SECONDS = 10

# Default sample size for sampling strategy
DEFAULT_SAMPLE_SIZE = 1000


class OverlapStrategy(str, Enum):
    """Strategy for computing value overlap."""

    FULL_COMPARISON = "full_comparison"  # Hash all distinct values
    SAMPLING = "sampling"  # Random sample for faster analysis


@dataclass
class OverlapResult:
    """Result of value overlap analysis between two columns.

    Attributes:
        source_table: Source table name
        source_column: Source column name
        target_table: Target table name
        target_column: Target column name
        overlap_score: Jaccard similarity (0.0-1.0)
        source_distinct_count: Number of distinct values in source
        target_distinct_count: Number of distinct values in target
        intersection_count: Number of values found in both columns
        strategy: Strategy used for analysis
        sample_size: Sample size if sampling strategy used
        analysis_time_ms: Time taken for analysis in milliseconds
        timed_out: Whether analysis timed out
    """

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    overlap_score: float
    source_distinct_count: int
    target_distinct_count: int
    intersection_count: int
    strategy: OverlapStrategy
    sample_size: int | None
    analysis_time_ms: int
    timed_out: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "source_table": self.source_table,
            "source_column": self.source_column,
            "target_table": self.target_table,
            "target_column": self.target_column,
            "overlap_score": self.overlap_score,
            "source_distinct_count": self.source_distinct_count,
            "target_distinct_count": self.target_distinct_count,
            "intersection_count": self.intersection_count,
            "strategy": self.strategy.value,
            "sample_size": self.sample_size,
            "analysis_time_ms": self.analysis_time_ms,
            "timed_out": self.timed_out,
        }


class ValueOverlapAnalyzer:
    """Analyzes value overlap between columns for FK inference.

    Uses actual data values to determine if a column likely references
    another column. High overlap (source values mostly exist in target)
    indicates a likely FK relationship.

    Supports two strategies:
    - full_comparison: Compare all distinct values (accurate, slower)
    - sampling: Compare random sample (faster, approximate)

    T146: Tracks performance metrics via src/metrics.py.

    Attributes:
        engine: SQLAlchemy database engine
        timeout_seconds: Maximum time per column pair analysis
        default_sample_size: Default sample size for sampling strategy
    """

    def __init__(
        self,
        engine: Engine,
        timeout_seconds: float = DEFAULT_OVERLAP_TIMEOUT_SECONDS,
        default_sample_size: int = DEFAULT_SAMPLE_SIZE,
    ):
        """Initialize the analyzer.

        Args:
            engine: SQLAlchemy engine for database access
            timeout_seconds: Maximum time for overlap analysis per pair
            default_sample_size: Default N for sampling strategy
        """
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self.default_sample_size = default_sample_size
        self._metrics = get_metrics()

    def calculate_overlap(
        self,
        source_table: str,
        source_column: str,
        source_schema: str,
        target_table: str,
        target_column: str,
        target_schema: str,
        strategy: OverlapStrategy = OverlapStrategy.SAMPLING,
        sample_size: int | None = None,
    ) -> OverlapResult:
        """Calculate value overlap between two columns.

        Computes the Jaccard similarity: |A ∩ B| / |A ∪ B|
        For FK inference, we also track the containment ratio: |A ∩ B| / |A|
        which indicates what percentage of source values exist in target.

        Args:
            source_table: Source table name (FK side)
            source_column: Source column name
            source_schema: Source schema name
            target_table: Target table name (PK side)
            target_column: Target column name
            target_schema: Target schema name
            strategy: Analysis strategy (full_comparison or sampling)
            sample_size: Sample size for sampling strategy (default: 1000)

        Returns:
            OverlapResult with similarity scores and metrics
        """
        start_time = time.time()
        timed_out = False

        # Use default sample size if not specified
        if sample_size is None:
            sample_size = self.default_sample_size

        # Track with performance metrics
        operation_name = f"overlap_{strategy.value}"

        try:
            with self._metrics.track(operation_name):
                if strategy == OverlapStrategy.FULL_COMPARISON:
                    result = self._full_comparison(
                        source_table=source_table,
                        source_column=source_column,
                        source_schema=source_schema,
                        target_table=target_table,
                        target_column=target_column,
                        target_schema=target_schema,
                    )
                else:
                    result = self._sampling_comparison(
                        source_table=source_table,
                        source_column=source_column,
                        source_schema=source_schema,
                        target_table=target_table,
                        target_column=target_column,
                        target_schema=target_schema,
                        sample_size=sample_size,
                    )

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self.timeout_seconds:
                    timed_out = True
                    logger.warning(
                        f"Overlap analysis timed out after {elapsed:.1f}s for "
                        f"{source_schema}.{source_table}.{source_column} -> "
                        f"{target_schema}.{target_table}.{target_column}"
                    )

                elapsed_ms = int((time.time() - start_time) * 1000)

                return OverlapResult(
                    source_table=f"{source_schema}.{source_table}",
                    source_column=source_column,
                    target_table=f"{target_schema}.{target_table}",
                    target_column=target_column,
                    overlap_score=result["overlap_score"],
                    source_distinct_count=result["source_distinct_count"],
                    target_distinct_count=result["target_distinct_count"],
                    intersection_count=result["intersection_count"],
                    strategy=strategy,
                    sample_size=sample_size if strategy == OverlapStrategy.SAMPLING else None,
                    analysis_time_ms=elapsed_ms,
                    timed_out=timed_out,
                )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Overlap analysis failed for {source_schema}.{source_table}.{source_column}: {e}"
            )
            # Return zero overlap on error
            return OverlapResult(
                source_table=f"{source_schema}.{source_table}",
                source_column=source_column,
                target_table=f"{target_schema}.{target_table}",
                target_column=target_column,
                overlap_score=0.0,
                source_distinct_count=0,
                target_distinct_count=0,
                intersection_count=0,
                strategy=strategy,
                sample_size=sample_size if strategy == OverlapStrategy.SAMPLING else None,
                analysis_time_ms=elapsed_ms,
                timed_out=True,
            )

    def _full_comparison(
        self,
        source_table: str,
        source_column: str,
        source_schema: str,
        target_table: str,
        target_column: str,
        target_schema: str,
    ) -> dict:
        """Perform full comparison of all distinct values.

        Uses SQL to compute the intersection directly, avoiding
        pulling all values into Python.

        Args:
            source_table: Source table name
            source_column: Source column name
            source_schema: Source schema name
            target_table: Target table name
            target_column: Target column name
            target_schema: Target schema name

        Returns:
            Dict with overlap_score, distinct counts, and intersection count
        """
        with self.engine.connect() as conn:
            # Get source distinct count
            source_count_query = text(f"""
                SELECT COUNT(DISTINCT [{source_column}])
                FROM [{source_schema}].[{source_table}]
                WHERE [{source_column}] IS NOT NULL
            """)
            source_distinct = conn.execute(source_count_query).scalar() or 0

            # Get target distinct count
            target_count_query = text(f"""
                SELECT COUNT(DISTINCT [{target_column}])
                FROM [{target_schema}].[{target_table}]
                WHERE [{target_column}] IS NOT NULL
            """)
            target_distinct = conn.execute(target_count_query).scalar() or 0

            # Get intersection count (values in both)
            intersection_query = text(f"""
                SELECT COUNT(*)
                FROM (
                    SELECT DISTINCT [{source_column}] AS val
                    FROM [{source_schema}].[{source_table}]
                    WHERE [{source_column}] IS NOT NULL
                    INTERSECT
                    SELECT DISTINCT [{target_column}] AS val
                    FROM [{target_schema}].[{target_table}]
                    WHERE [{target_column}] IS NOT NULL
                ) AS intersection
            """)
            intersection_count = conn.execute(intersection_query).scalar() or 0

            # Calculate Jaccard similarity: |A ∩ B| / |A ∪ B|
            # |A ∪ B| = |A| + |B| - |A ∩ B|
            union_count = source_distinct + target_distinct - intersection_count

            if union_count == 0:
                overlap_score = 0.0
            else:
                overlap_score = intersection_count / union_count

            logger.debug(
                f"Full comparison: {source_schema}.{source_table}.{source_column} -> "
                f"{target_schema}.{target_table}.{target_column}: "
                f"intersection={intersection_count}, union={union_count}, score={overlap_score:.3f}"
            )

            return {
                "overlap_score": round(overlap_score, 4),
                "source_distinct_count": source_distinct,
                "target_distinct_count": target_distinct,
                "intersection_count": intersection_count,
            }

    def _sampling_comparison(
        self,
        source_table: str,
        source_column: str,
        source_schema: str,
        target_table: str,
        target_column: str,
        target_schema: str,
        sample_size: int,
    ) -> dict:
        """Perform sampling-based comparison for faster analysis.

        Takes a random sample of source values and checks how many
        exist in the target column. More efficient for large tables.

        Args:
            source_table: Source table name
            source_column: Source column name
            source_schema: Source schema name
            target_table: Target table name
            target_column: Target column name
            target_schema: Target schema name
            sample_size: Number of values to sample

        Returns:
            Dict with overlap_score, distinct counts, and intersection count
        """
        with self.engine.connect() as conn:
            # Sample distinct values from source using TABLESAMPLE or TOP with ORDER BY NEWID()
            # NEWID() provides true random sampling
            sample_query = text(f"""
                SELECT DISTINCT TOP ({sample_size}) [{source_column}] AS val
                FROM [{source_schema}].[{source_table}]
                WHERE [{source_column}] IS NOT NULL
                ORDER BY NEWID()
            """)
            source_samples = [row[0] for row in conn.execute(sample_query).fetchall()]
            source_sample_count = len(source_samples)

            if source_sample_count == 0:
                return {
                    "overlap_score": 0.0,
                    "source_distinct_count": 0,
                    "target_distinct_count": 0,
                    "intersection_count": 0,
                }

            # Get target distinct count (approximate with sample if large)
            target_count_query = text(f"""
                SELECT COUNT(DISTINCT [{target_column}])
                FROM [{target_schema}].[{target_table}]
                WHERE [{target_column}] IS NOT NULL
            """)
            target_distinct = conn.execute(target_count_query).scalar() or 0

            # Check how many sampled source values exist in target
            # Create a temp table or use IN clause (IN clause is simpler for moderate samples)
            if source_sample_count > 0:
                # Use parameterized query for safety
                # For SQL Server, we need to construct the IN clause carefully
                placeholders = ", ".join([f":val_{i}" for i in range(len(source_samples))])
                params = {f"val_{i}": v for i, v in enumerate(source_samples)}

                match_query = text(f"""
                    SELECT COUNT(DISTINCT [{target_column}])
                    FROM [{target_schema}].[{target_table}]
                    WHERE [{target_column}] IN ({placeholders})
                """)
                intersection_count = conn.execute(match_query, params).scalar() or 0
            else:
                intersection_count = 0

            # Calculate overlap based on sample
            # This gives us the containment ratio (what % of source exists in target)
            # which is more relevant for FK inference than Jaccard
            if source_sample_count == 0:
                overlap_score = 0.0
            else:
                # Containment-based overlap: what fraction of source values exist in target
                overlap_score = intersection_count / source_sample_count

            logger.debug(
                f"Sampling comparison ({sample_size}): "
                f"{source_schema}.{source_table}.{source_column} -> "
                f"{target_schema}.{target_table}.{target_column}: "
                f"sampled={source_sample_count}, matches={intersection_count}, score={overlap_score:.3f}"
            )

            return {
                "overlap_score": round(overlap_score, 4),
                "source_distinct_count": source_sample_count,
                "target_distinct_count": target_distinct,
                "intersection_count": intersection_count,
            }

    def get_overlap_stats(self) -> dict:
        """Get performance statistics for overlap analysis.

        Returns:
            Dict with performance metrics for full_comparison and sampling
        """
        return {
            "full_comparison": self._metrics.get_stats("overlap_full_comparison"),
            "sampling": self._metrics.get_stats("overlap_sampling"),
        }
