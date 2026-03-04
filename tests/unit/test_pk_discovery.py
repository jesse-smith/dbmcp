"""Unit tests for PKDiscovery class.

Tests PK candidate discovery including constraint-backed detection,
structural candidate analysis, and type filtering.
"""

from unittest.mock import MagicMock

from src.analysis.pk_discovery import DEFAULT_PK_TYPE_FILTER, PKDiscovery

# ---------------------------------------------------------------------------
# Helpers to build mock result rows
# ---------------------------------------------------------------------------

def _mock_result(rows):
    """Create a mock execute result that returns the given rows via fetchall."""
    mock = MagicMock()
    mock.fetchall.return_value = rows
    return mock


def _mock_scalar(value):
    """Create a mock execute result that returns a scalar value."""
    mock = MagicMock()
    mock.scalar.return_value = value
    return mock


# ---------------------------------------------------------------------------
# Constraint-backed PK detection
# ---------------------------------------------------------------------------

class TestConstraintBacked:
    """Tests for detecting PK/UNIQUE constraint-backed candidates."""

    def test_primary_key_detected(self):
        """A column with a PRIMARY KEY constraint is detected."""
        conn = MagicMock()
        # Query for PK constraint columns
        pk_rows = [("order_id", "int", "PRIMARY KEY")]
        # Query for UNIQUE constraint columns
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert len(candidates) == 1
        assert candidates[0].column_name == "order_id"
        assert candidates[0].data_type == "int"
        assert candidates[0].is_constraint_backed is True
        assert candidates[0].constraint_type == "PRIMARY KEY"

    def test_unique_constraint_detected(self):
        """A column with a UNIQUE constraint is detected."""
        conn = MagicMock()
        pk_rows = []
        uq_rows = [("email", "varchar")]
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "users")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert len(candidates) == 1
        assert candidates[0].column_name == "email"
        assert candidates[0].is_constraint_backed is True
        assert candidates[0].constraint_type == "UNIQUE"

    def test_pk_and_unique_both_detected(self):
        """Both PK and UNIQUE columns appear in results."""
        conn = MagicMock()
        pk_rows = [("id", "int", "PRIMARY KEY")]
        uq_rows = [("code", "varchar")]
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "products")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert len(candidates) == 2
        names = {c.column_name for c in candidates}
        assert names == {"id", "code"}

    def test_no_constraints_returns_empty(self):
        """A table with no PK or UNIQUE constraints returns empty list."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([]),
            _mock_result([]),
        ]

        discovery = PKDiscovery(conn, "dbo", "logs")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert candidates == []

    def test_is_pk_type_respects_custom_type_filter(self):
        """A PK column whose type is not in the filter gets is_pk_type=False."""
        conn = MagicMock()
        pk_rows = [("id", "bigint", "PRIMARY KEY")]
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_constraint_candidates(
            type_filter=["uniqueidentifier"],
        )

        assert len(candidates) == 1
        assert candidates[0].column_name == "id"
        assert candidates[0].is_constraint_backed is True
        assert candidates[0].is_pk_type is False

    def test_is_pk_type_true_with_empty_type_filter(self):
        """An empty type filter means all types qualify as pk_type."""
        conn = MagicMock()
        pk_rows = [("id", "varchar", "PRIMARY KEY")]
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert len(candidates) == 1
        assert candidates[0].is_pk_type is True


# ---------------------------------------------------------------------------
# Structural candidate detection
# ---------------------------------------------------------------------------

class TestStructuralCandidates:
    """Tests for structural PK candidacy (unique + non-null + type match)."""

    def test_structural_candidate_found(self):
        """Column with unique values, no nulls, and matching type is a candidate."""
        conn = MagicMock()

        # get_all_columns returns (column_name, data_type, is_nullable)
        all_cols = [("tracking_id", "bigint", "NO")]
        # uniqueness check: COUNT(DISTINCT col) and COUNT(*) WHERE col IS NOT NULL
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [100, 100][idx]

        conn.execute.side_effect = [
            _mock_result(all_cols),      # get all columns
            _mock_result([uniqueness_row]),  # uniqueness check
        ]

        discovery = PKDiscovery(conn, "dbo", "shipments")
        candidates = discovery.get_structural_candidates(
            type_filter=["int", "bigint", "smallint", "tinyint", "uniqueidentifier"],
            exclude_columns=set(),
        )

        assert len(candidates) == 1
        assert candidates[0].column_name == "tracking_id"
        assert candidates[0].is_constraint_backed is False
        assert candidates[0].constraint_type is None
        assert candidates[0].is_unique is True
        assert candidates[0].is_non_null is True
        assert candidates[0].is_pk_type is True

    def test_varchar_excluded_by_default_type_filter(self):
        """VARCHAR columns are excluded by the default type filter."""
        conn = MagicMock()
        all_cols = [("name", "varchar", "NO")]
        conn.execute.side_effect = [
            _mock_result(all_cols),
        ]

        discovery = PKDiscovery(conn, "dbo", "users")
        candidates = discovery.get_structural_candidates(
            type_filter=["int", "bigint", "smallint", "tinyint", "uniqueidentifier"],
            exclude_columns=set(),
        )

        # varchar doesn't match default type filter, so no candidates
        assert candidates == []

    def test_custom_type_filter_includes_varchar(self):
        """Custom type_filter can include VARCHAR columns."""
        conn = MagicMock()
        all_cols = [("code", "varchar", "NO")]
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [50, 50][idx]

        conn.execute.side_effect = [
            _mock_result(all_cols),
            _mock_result([uniqueness_row]),
        ]

        discovery = PKDiscovery(conn, "dbo", "categories")
        candidates = discovery.get_structural_candidates(
            type_filter=["varchar"],
            exclude_columns=set(),
        )

        assert len(candidates) == 1
        assert candidates[0].column_name == "code"
        assert candidates[0].is_pk_type is True

    def test_nullable_column_not_structural_candidate(self):
        """A nullable column is not a structural PK candidate (even if unique)."""
        conn = MagicMock()
        all_cols = [("optional_id", "int", "YES")]

        conn.execute.side_effect = [
            _mock_result(all_cols),
        ]

        discovery = PKDiscovery(conn, "dbo", "events")
        candidates = discovery.get_structural_candidates(
            type_filter=["int", "bigint"],
            exclude_columns=set(),
        )

        # Nullable columns excluded early
        assert candidates == []

    def test_non_unique_column_not_structural_candidate(self):
        """A column with duplicate values is not a structural candidate."""
        conn = MagicMock()
        all_cols = [("status_id", "int", "NO")]
        # distinct_count < total_count means not unique
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [5, 100][idx]

        conn.execute.side_effect = [
            _mock_result(all_cols),
            _mock_result([uniqueness_row]),
        ]

        discovery = PKDiscovery(conn, "dbo", "tasks")
        candidates = discovery.get_structural_candidates(
            type_filter=["int"],
            exclude_columns=set(),
        )

        assert candidates == []

    def test_constraint_columns_excluded(self):
        """Columns already found via constraints are skipped in structural check."""
        conn = MagicMock()
        all_cols = [("id", "int", "NO"), ("tracking_id", "bigint", "NO")]
        # Only tracking_id checked (id excluded)
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [100, 100][idx]

        conn.execute.side_effect = [
            _mock_result(all_cols),
            _mock_result([uniqueness_row]),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_structural_candidates(
            type_filter=["int", "bigint"],
            exclude_columns={"id"},  # Already found via constraint
        )

        assert len(candidates) == 1
        assert candidates[0].column_name == "tracking_id"

    def test_empty_type_filter_disables_type_check(self):
        """Empty type_filter list means all types are considered."""
        conn = MagicMock()
        all_cols = [("uuid_col", "varchar", "NO")]
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [50, 50][idx]

        conn.execute.side_effect = [
            _mock_result(all_cols),
            _mock_result([uniqueness_row]),
        ]

        discovery = PKDiscovery(conn, "dbo", "items")
        candidates = discovery.get_structural_candidates(
            type_filter=[],  # Empty = disable type filtering
            exclude_columns=set(),
        )

        assert len(candidates) == 1
        assert candidates[0].is_pk_type is True  # All types match when filter is empty


# ---------------------------------------------------------------------------
# Full find_candidates (combines constraint + structural)
# ---------------------------------------------------------------------------

class TestFindCandidates:
    """Tests for the combined find_candidates method."""

    def test_combines_constraint_and_structural(self):
        """find_candidates merges constraint-backed and structural results."""
        conn = MagicMock()

        # Constraint queries: PK on "id"
        pk_rows = [("id", "int", "PRIMARY KEY")]
        uq_rows = []
        # Structural queries: all columns, then uniqueness check for tracking_id
        all_cols = [("id", "int", "NO"), ("tracking_id", "bigint", "NO"), ("name", "varchar", "YES")]
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [100, 100][idx]

        conn.execute.side_effect = [
            _mock_result(pk_rows),           # constraint: PK
            _mock_result(uq_rows),           # constraint: UNIQUE
            _mock_result(all_cols),           # structural: all columns
            _mock_result([uniqueness_row]),   # structural: uniqueness for tracking_id
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.find_candidates()

        assert len(candidates) == 2
        names = [c.column_name for c in candidates]
        assert "id" in names
        assert "tracking_id" in names

    def test_no_candidates_returns_empty(self):
        """Table with no PK-worthy columns returns empty list."""
        conn = MagicMock()

        pk_rows = []
        uq_rows = []
        # All columns are nullable or non-unique
        all_cols = [("col1", "varchar", "YES"), ("col2", "int", "YES")]

        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
            _mock_result(all_cols),
        ]

        discovery = PKDiscovery(conn, "dbo", "logs")
        candidates = discovery.find_candidates()

        assert candidates == []

    def test_default_type_filter_applied(self):
        """Default type filter excludes varchar from structural check."""
        conn = MagicMock()

        pk_rows = []
        uq_rows = []
        all_cols = [("code", "varchar", "NO")]

        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
            _mock_result(all_cols),
        ]

        discovery = PKDiscovery(conn, "dbo", "settings")
        candidates = discovery.find_candidates()  # Uses default type_filter

        assert candidates == []

    def test_custom_type_filter_override(self):
        """Custom type_filter passed to find_candidates overrides default."""
        conn = MagicMock()

        pk_rows = []
        uq_rows = []
        all_cols = [("code", "varchar", "NO")]
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [25, 25][idx]

        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
            _mock_result(all_cols),
            _mock_result([uniqueness_row]),
        ]

        discovery = PKDiscovery(conn, "dbo", "settings")
        candidates = discovery.find_candidates(type_filter=["varchar"])

        assert len(candidates) == 1
        assert candidates[0].column_name == "code"

    def test_constraint_pk_fields_populated(self):
        """Constraint-backed candidate has correct is_unique and is_non_null fields."""
        conn = MagicMock()

        pk_rows = [("id", "int", "PRIMARY KEY")]
        uq_rows = []
        all_cols = [("id", "int", "NO")]

        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
            _mock_result(all_cols),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.find_candidates()

        pk_candidate = next(c for c in candidates if c.column_name == "id")
        assert pk_candidate.is_constraint_backed is True
        assert pk_candidate.constraint_type == "PRIMARY KEY"
        # PK constraint implies unique and non-null
        assert pk_candidate.is_unique is True
        assert pk_candidate.is_non_null is True


# ---------------------------------------------------------------------------
# Default schema behavior
# ---------------------------------------------------------------------------

class TestDefaultSchema:
    """Tests for schema handling."""

    def test_uses_provided_schema(self):
        """PKDiscovery uses the provided schema name in queries."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([]),
            _mock_result([]),
            _mock_result([]),
        ]

        discovery = PKDiscovery(conn, "sales", "orders")
        discovery.find_candidates()

        # Verify schema_name was used in queries
        assert discovery.schema_name == "sales"
