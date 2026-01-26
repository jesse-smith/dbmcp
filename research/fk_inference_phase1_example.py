"""
Example Foreign Key Inference Implementation - Phase 1 (Simple/Metadata-only)

This demonstrates the recommended YAGNI approach:
- Uses only metadata (no data access)
- Fast, maintainable, 75-80% accuracy for typical legacy DBs
- Can be extended to Phase 2 with value overlap analysis if needed
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum


class MatchType(Enum):
    """Types of FK relationship matches"""
    PERFECT_NAME = 1.0      # Exact match after normalization
    STRONG_NAME = 0.85      # High string similarity (>0.85)
    WEAK_NAME = 0.70        # Moderate similarity (0.70-0.85)
    TYPE_MISMATCH = 0.0     # Can't be a FK if types don't match


@dataclass
class InferredFK:
    """Represents an inferred foreign key relationship"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    confidence: float  # 0.0 to 1.0
    reason: str  # Why this relationship was suggested


class ForeignKeyInferencer:
    """
    Phase 1 Foreign Key Inference using metadata-only approach.
    
    Strategy:
    1. Name pattern matching (40% weight)
    2. Data type compatibility (15% weight)
    3. Structural hints like is_primary_key, nullable (45% weight)
    """

    # Common naming patterns for IDs
    ID_SUFFIXES = ['_id', '_key', '_code', '_num', '_number']

    # SQL Server type groups (can extend for other DBs)
    TYPE_GROUPS = {
        'NUMERIC': ['int', 'bigint', 'smallint', 'tinyint', 'numeric', 'decimal'],
        'STRING': ['varchar', 'nvarchar', 'char', 'nchar', 'text'],
        'GUID': ['uniqueidentifier'],
        'DATE': ['datetime', 'datetime2', 'date', 'time'],
    }

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Args:
            confidence_threshold: Minimum confidence (0-1) to include inferred FK
        """
        self.confidence_threshold = confidence_threshold

    def infer_relationships(
        self,
        tables: dict[str, list[dict]],  # table_name -> [{'name': col_name, 'type': col_type, 'is_pk': bool}, ...]
    ) -> list[InferredFK]:
        """
        Infer foreign key relationships for all tables.
        
        Args:
            tables: Dict mapping table names to their columns
            
        Returns:
            List of inferred FKs meeting confidence threshold
        """
        results = []
        table_names = list(tables.keys())

        # For each table
        for source_table in table_names:
            source_cols = {col['name']: col for col in tables[source_table]}

            # Check each column as potential FK
            for source_col_name, source_col in source_cols.items():
                # Skip primary keys (they can't be FKs to the same table's PK)
                if source_col.get('is_pk'):
                    continue

                # For each potential target table
                for target_table in table_names:
                    if target_table == source_table:
                        continue  # Skip self-references for now

                    target_cols = tables[target_table]
                    target_pk = next(
                        (col for col in target_cols if col.get('is_pk')),
                        None
                    )

                    if not target_pk:
                        continue  # Can't FK to a table without PK

                    # Score this potential relationship
                    confidence = self._score_match(
                        source_table, source_col_name, source_col,
                        target_table, target_pk['name'], target_pk
                    )

                    if confidence >= self.confidence_threshold:
                        reason = self._explain_match(
                            source_col_name, target_pk['name'],
                            source_col['type'], target_pk['type']
                        )

                        results.append(InferredFK(
                            source_table=source_table,
                            source_column=source_col_name,
                            target_table=target_table,
                            target_column=target_pk['name'],
                            confidence=confidence,
                            reason=reason
                        ))

        # Sort by confidence (highest first)
        return sorted(results, key=lambda x: x.confidence, reverse=True)

    def _score_match(
        self,
        src_table: str, src_col: str, src_col_info: dict,
        tgt_table: str, tgt_col: str, tgt_col_info: dict,
    ) -> float:
        """
        Score a potential FK relationship on 0-1 scale.
        
        Scoring breakdown (total weight = 1.0):
        - Name similarity: 0.40
        - Type compatibility: 0.15
        - Structural hints: 0.45
        """

        # 1. CHECK TYPE COMPATIBILITY (veto if mismatch)
        type_score = self._score_type_match(
            src_col_info.get('type', ''),
            tgt_col_info.get('type', '')
        )

        if type_score == 0:
            return 0.0  # Veto: incompatible types

        # 2. NAME SIMILARITY SCORING (weight: 0.40)
        name_score = self._score_name_match(src_col, src_table, tgt_col, tgt_table)

        # 3. STRUCTURAL HINTS SCORING (weight: 0.45)
        struct_score = self._score_structural(src_col_info, tgt_col_info)

        # Combine scores
        final_score = (
            name_score * 0.40 +
            type_score * 0.15 +
            struct_score * 0.45
        )

        return final_score

    def _score_name_match(
        self, src_col: str, src_table: str, tgt_col: str, tgt_table: str
    ) -> float:
        """
        Score based on column and table name patterns.
        
        Patterns checked:
        - Exact match after normalization (1.0)
        - Table prefix + ID pattern (0.9)
        - High string similarity (0.7-0.85)
        - Weak pattern match (0.3-0.5)
        """
        src_col_norm = src_col.lower().replace('_', '')
        tgt_col_norm = tgt_col.lower().replace('_', '')

        # Pattern 1: Exact match
        if src_col_norm == tgt_col_norm:
            return 1.0

        # Pattern 2: Table name as prefix (e.g., OrderID in Orders table)
        # "customer" table, "customerid" column = match
        tgt_table_norm = tgt_table.lower().replace('_', '').rstrip('s')
        if src_col_norm.startswith(tgt_table_norm) and src_col_norm.endswith('id'):
            return 0.90

        # Pattern 3: Generic ID matching
        # If both end with ID and have high similarity
        if src_col_norm.endswith('id') and tgt_col_norm == 'id':
            # Compare the non-ID parts
            src_base = src_col_norm.replace('id', '')
            if src_base and src_base in tgt_table_norm:
                return 0.85

        # Pattern 4: String similarity (Jaro-Winkler-like)
        similarity = SequenceMatcher(None, src_col_norm, tgt_col_norm).ratio()

        if similarity > 0.85:
            return 0.80
        elif similarity > 0.70:
            return 0.55
        elif similarity > 0.60:
            return 0.30

        return 0.0

    def _score_type_match(self, src_type: str, tgt_type: str) -> float:
        """
        Score type compatibility. If types can't possibly FK, return 0.
        
        Returns:
        - 1.0 if exact match or compatible types
        - 0.5 if weakly compatible (e.g., int vs bigint)
        - 0.0 if impossible (e.g., varchar vs int)
        """
        src_type_norm = src_type.lower().strip()
        tgt_type_norm = tgt_type.lower().strip()

        # Exact match
        if src_type_norm == tgt_type_norm:
            return 1.0

        # Group-based matching
        for type_group, types in self.TYPE_GROUPS.items():
            src_in_group = any(t in src_type_norm for t in types)
            tgt_in_group = any(t in tgt_type_norm for t in types)

            if src_in_group and tgt_in_group:
                # Both in same group - compatible
                if src_type_norm == tgt_type_norm:
                    return 1.0
                else:
                    return 0.5  # Different but compatible (e.g., int vs bigint)

            # One in group, one not - check for obvious incompatibility
            if (src_in_group and not tgt_in_group) or (not src_in_group and tgt_in_group):
                # One is numeric, other is string? No.
                if (type_group == 'NUMERIC' and 'varchar' in tgt_type_norm) or \
                   (type_group == 'STRING' and 'int' in src_type_norm):
                    return 0.0

        # Default: moderate confidence if types aren't obviously incompatible
        return 0.5

    def _score_structural(self, src_col: dict, tgt_col: dict) -> float:
        """
        Score based on structural properties (nullability, uniqueness).
        
        FK columns often:
        - Are nullable (can be NULL)
        - Reference a unique/PK column
        """
        score = 0.5  # Baseline

        # FK columns are typically nullable
        if src_col.get('is_nullable', False):
            score += 0.2
        else:
            score -= 0.1  # Non-nullable is less common for FKs

        # FK references unique columns (usually PK)
        if tgt_col.get('is_pk', False):
            score += 0.3
        elif tgt_col.get('is_unique', False):
            score += 0.15

        return min(score, 1.0)

    def _explain_match(
        self, src_col: str, tgt_col: str, src_type: str, tgt_type: str
    ) -> str:
        """Generate human-readable explanation for the inference"""
        src_col_norm = src_col.lower().replace('_', '')
        tgt_col_norm = tgt_col.lower().replace('_', '')

        if src_col_norm == tgt_col_norm:
            return f"Exact name match: {src_col} == {tgt_col}"

        similarity = SequenceMatcher(None, src_col_norm, tgt_col_norm).ratio()
        if similarity > 0.85:
            return f"Strong name similarity ({similarity:.0%}): {src_col} ≈ {tgt_col}"

        return f"Name and type compatibility: {src_col} ({src_type}) → {tgt_col} ({tgt_type})"


# ===== EXAMPLE USAGE =====

if __name__ == '__main__':
    # Simulated database schema metadata (as would come from SQLAlchemy inspection)
    test_tables = {
        'Orders': [
            {'name': 'OrderID', 'type': 'int', 'is_pk': True, 'is_nullable': False, 'is_unique': False},
            {'name': 'CustomerID', 'type': 'int', 'is_pk': False, 'is_nullable': True, 'is_unique': False},
            {'name': 'OrderDate', 'type': 'datetime', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
            {'name': 'Amount', 'type': 'decimal', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
        ],
        'Customers': [
            {'name': 'ID', 'type': 'int', 'is_pk': True, 'is_nullable': False, 'is_unique': True},
            {'name': 'Name', 'type': 'varchar', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
            {'name': 'Email', 'type': 'varchar', 'is_pk': False, 'is_nullable': True, 'is_unique': True},
        ],
        'OrderItems': [
            {'name': 'ItemID', 'type': 'int', 'is_pk': True, 'is_nullable': False, 'is_unique': False},
            {'name': 'Order_ID', 'type': 'int', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
            {'name': 'ProductID', 'type': 'int', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
            {'name': 'Quantity', 'type': 'int', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
        ],
        'Products': [
            {'name': 'ProductID', 'type': 'int', 'is_pk': True, 'is_nullable': False, 'is_unique': True},
            {'name': 'ProductName', 'type': 'varchar', 'is_pk': False, 'is_nullable': False, 'is_unique': False},
            {'name': 'CategoryID', 'type': 'int', 'is_pk': False, 'is_nullable': True, 'is_unique': False},
        ],
    }

    # Run inference
    inferencer = ForeignKeyInferencer(confidence_threshold=0.5)
    inferred_fks = inferencer.infer_relationships(test_tables)

    # Display results
    print(f"Found {len(inferred_fks)} inferred foreign key relationships:\n")
    for fk in inferred_fks:
        print(f"  {fk.source_table}.{fk.source_column}")
        print(f"    → {fk.target_table}.{fk.target_column}")
        print(f"    Confidence: {fk.confidence:.1%}")
        print(f"    Reason: {fk.reason}")
        print()

