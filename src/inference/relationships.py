"""Foreign key inference algorithm.

This module implements Phase 1 (metadata-only) FK inference using
three-factor weighted scoring:
- Name similarity (40% weight)
- Type compatibility (15% weight, veto if incompatible)
- Structural hints (45% weight)

Target accuracy: 75-80% for typical legacy databases.

T134: Supports configurable timeout with partial results.
"""

import time
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.relationship import InferenceFactors, InferredFK, create_relationship_id

logger = get_logger(__name__)

# Default timeout for inference operations (10 seconds)
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 10


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
    """Infers foreign key relationships from metadata.

    Uses three-factor weighted scoring:
    - Name similarity (40%): Column name pattern matching
    - Type compatibility (15%): Data type group matching
    - Structural hints (45%): PK, nullable, unique index indicators

    T134: Supports configurable timeout with partial results.

    Attributes:
        engine: SQLAlchemy database engine
        threshold: Minimum confidence score to return (default: 0.50)
        timeout_seconds: Maximum time for inference before returning partial results
    """

    def __init__(
        self,
        engine: Engine,
        threshold: float = 0.50,
        timeout_seconds: float | None = None,
    ):
        """Initialize the inferencer.

        Args:
            engine: SQLAlchemy engine for database access
            threshold: Minimum confidence threshold (0.0-1.0)
            timeout_seconds: Maximum inference time (None = default 10s, 0 = no timeout)
        """
        self.engine = engine
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_INFERENCE_TIMEOUT_SECONDS
        self._inspector = None
        self._column_cache: dict[str, list[ColumnInfo]] = {}

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
    ) -> tuple[list[InferredFK], dict]:
        """Infer foreign key relationships for a table.

        T134: Supports timeout with partial results. If inference exceeds
        timeout_seconds, returns partial results with timed_out=True in metadata.

        Args:
            table_name: Source table to analyze
            schema_name: Schema containing the table
            max_candidates: Maximum candidates to return
            include_value_overlap: If True, raises NotImplementedError (Phase 2 feature)

        Returns:
            Tuple of (inferred relationships, analysis metadata)
            Metadata includes: analysis_time_ms, total_candidates_evaluated, timed_out, tables_analyzed

        Raises:
            NotImplementedError: If include_value_overlap=True (Phase 2 feature)
            ValueError: If parameters are invalid
        """
        # Parameter validation
        if include_value_overlap:
            raise NotImplementedError("Value overlap analysis available in Phase 2")

        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")

        if max_candidates < 1 or max_candidates > 1000:
            raise ValueError("max_candidates must be between 1 and 1000")

        start_time = time.time()
        total_evaluated = 0
        tables_analyzed = 0
        timed_out = False

        # Get source table columns
        source_columns = self._get_columns(table_name, schema_name)
        if not source_columns:
            logger.warning(f"No columns found for {schema_name}.{table_name}")
            return [], {"analysis_time_ms": 0, "total_candidates_evaluated": 0, "timed_out": False, "tables_analyzed": 0}

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

                # Score this potential relationship
                score, factors = self._calculate_confidence(src_col, target_pk, target_table)

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
        self, src_col: ColumnInfo, tgt_col: ColumnInfo, tgt_table: str
    ) -> tuple[float, InferenceFactors]:
        """Calculate confidence score using three-factor weighted scoring.

        Returns:
            Tuple of (score, factors)
        """
        # Factor 1: Type compatibility (veto if incompatible)
        type_compatible = self._check_type_compatibility(src_col.data_type, tgt_col.data_type)
        if not type_compatible:
            return 0.0, InferenceFactors(name_similarity=0, type_compatible=False)

        # Factor 2: Name similarity (40% weight)
        name_score = self._calculate_name_similarity(src_col.name, tgt_col.name, tgt_table)

        # Factor 3: Structural hints (45% weight)
        structural_score, hints = self._calculate_structural_score(src_col, tgt_col)

        # Combine scores: 40% name + 15% type + 45% structural
        # Type is binary (1.0 if compatible), so it contributes 0.15 when compatible
        final_score = (name_score * 0.40) + (1.0 * 0.15) + (structural_score * 0.45)

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

        return " + ".join(parts) if parts else "Pattern match"

    def clear_cache(self):
        """Clear the column metadata cache."""
        self._column_cache.clear()
        self._inspector = None
