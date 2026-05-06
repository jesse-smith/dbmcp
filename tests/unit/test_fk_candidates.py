"""Unit tests for FKCandidateSearch class.

Tests FK candidate discovery including target table resolution,
PK filtering, structural metadata collection, value overlap,
and result limiting.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.analysis.fk_candidates import FKCandidateSearch
from src.models.analysis import PKCandidate

# ---------------------------------------------------------------------------
# Helpers to build mock result rows
# ---------------------------------------------------------------------------

def _mock_result(rows):
    """Create a mock execute result that returns the given rows via fetchall."""
    mock = MagicMock()
    mock.fetchall.return_value = rows
    mock.fetchone.return_value = rows[0] if rows else None
    return mock


def _mock_scalar(value):
    """Create a mock execute result that returns a scalar value."""
    mock = MagicMock()
    mock.scalar.return_value = value
    return mock


def _make_pk_candidate(column_name, data_type="int", constraint_type="PRIMARY KEY"):
    """Create a PKCandidate for testing."""
    return PKCandidate(
        column_name=column_name,
        data_type=data_type,
        is_constraint_backed=True,
        constraint_type=constraint_type,
        is_unique=True,
        is_non_null=True,
        is_pk_type=True,
    )


# ---------------------------------------------------------------------------
# Target table resolution
# ---------------------------------------------------------------------------

class TestTargetTableResolution:
    """Tests for resolving which target tables to search."""

    def test_default_schema_scoping(self):
        """When no target filters, defaults to source schema."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("SalesLT", "Customers"), ("SalesLT", "Products")]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="SalesLT",
            source_table="Orders",
            source_column="CustomerID",
            source_data_type="int",
        )
        tables = search.get_target_tables()

        assert ("SalesLT", "Customers") in tables
        # Verify the query used source schema
        call_args = conn.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("schema_name") == "SalesLT"

    def test_target_schema_filter(self):
        """target_schema overrides default schema scoping."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("auth", "Users"), ("auth", "Roles")]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="SalesLT",
            source_table="Orders",
            source_column="CustomerID",
            source_data_type="int",
        )
        search.get_target_tables(target_schema="auth")

        call_args = conn.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("schema_name") == "auth"

    def test_target_tables_list_filter(self):
        """Explicit target_tables list filters results."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("dbo", "Customers"), ("dbo", "Products")]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        tables = search.get_target_tables(target_tables=["Customers", "Products"])

        # Should only return tables in the filter list
        table_names = [t[1] for t in tables]
        for name in table_names:
            assert name in ["Customers", "Products"]

    def test_target_table_pattern_filter(self):
        """target_table_pattern uses LIKE matching."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("dbo", "Customers")]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        search.get_target_tables(target_table_pattern="Cust%")

        # Verify pattern was passed in query
        call_args = conn.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("table_pattern") == "Cust%"

    def test_excludes_source_table(self):
        """Source table is excluded from target list."""
        conn = MagicMock()
        # Returns source table + other tables
        conn.execute.side_effect = [
            _mock_result([("dbo", "Orders"), ("dbo", "Customers")]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        tables = search.get_target_tables()

        table_names = [t[1] for t in tables]
        assert "Orders" not in table_names


# ---------------------------------------------------------------------------
# PK filter behavior
# ---------------------------------------------------------------------------

class TestPKFilter:
    """Tests for pk_candidates_only filter."""

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_pk_filter_on_uses_pk_discovery(self, mock_pk_cls):
        """When pk_candidates_only=True, uses PKDiscovery to find target columns."""
        conn = MagicMock()
        mock_pk_instance = MagicMock()
        mock_pk_instance.find_candidates.return_value = [
            _make_pk_candidate("id", "int"),
        ]
        mock_pk_cls.return_value = mock_pk_instance

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        columns = search.get_candidate_columns(
            target_schema="dbo",
            target_table="Customers",
            pk_candidates_only=True,
        )

        mock_pk_cls.assert_called_once_with(
            connection=conn,
            schema_name="dbo",
            table_name="Customers",
            dialect=None,
            inspector=None,
        )
        assert len(columns) == 1
        assert columns[0]["column_name"] == "id"

    def test_pk_filter_off_returns_all_columns(self):
        """When pk_candidates_only=False, returns all columns from target table."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([
                ("id", "int", "NO"),
                ("name", "varchar", "YES"),
                ("email", "varchar", "NO"),
            ]),
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        columns = search.get_candidate_columns(
            target_schema="dbo",
            target_table="Customers",
            pk_candidates_only=False,
        )

        assert len(columns) == 3
        names = [c["column_name"] for c in columns]
        assert "id" in names
        assert "name" in names
        assert "email" in names


# ---------------------------------------------------------------------------
# Structural metadata collection
# ---------------------------------------------------------------------------

class TestStructuralMetadata:
    """Tests for collecting structural metadata about candidate columns."""

    def test_collects_pk_constraint(self):
        """Detects PK constraint on target column."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("PRIMARY KEY",)]),  # constraint check
            _mock_result([("idx_pk",)]),        # index check
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        metadata = search.get_column_metadata(
            target_schema="dbo",
            target_table="Customers",
            target_column="id",
            target_data_type="int",
            target_is_nullable=False,
        )

        assert metadata["target_is_primary_key"] is True
        assert metadata["target_has_index"] is True

    def test_detects_unique_constraint(self):
        """Detects UNIQUE constraint on target column."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("UNIQUE",)]),  # constraint check
            _mock_result([("idx_uq",)]),  # index check
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        metadata = search.get_column_metadata(
            target_schema="dbo",
            target_table="Customers",
            target_column="email",
            target_data_type="varchar",
            target_is_nullable=False,
        )

        assert metadata["target_is_unique"] is True
        assert metadata["target_has_index"] is True

    def test_no_constraints_or_indexes(self):
        """Column with no constraints or indexes returns False for all."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([]),  # no constraints
            _mock_result([]),  # no indexes
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        metadata = search.get_column_metadata(
            target_schema="dbo",
            target_table="Customers",
            target_column="notes",
            target_data_type="varchar",
            target_is_nullable=True,
        )

        assert metadata["target_is_primary_key"] is False
        assert metadata["target_is_unique"] is False
        assert metadata["target_is_nullable"] is True
        assert metadata["target_has_index"] is False


# ---------------------------------------------------------------------------
# Value overlap
# ---------------------------------------------------------------------------

class TestValueOverlap:
    """Tests for value overlap computation."""

    def test_overlap_returns_count_and_percentage(self):
        """Value overlap returns count and percentage."""
        conn = MagicMock()
        # Source distinct count
        conn.execute.side_effect = [
            _mock_result([(100,)]),  # source distinct count
            _mock_result([(85,)]),   # overlap count via INTERSECT
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        overlap = search.compute_overlap(
            target_schema="dbo",
            target_table="Customers",
            target_column="id",
        )

        assert overlap["overlap_count"] == 85
        assert overlap["overlap_percentage"] == 85.0

    def test_overlap_zero_source_distinct(self):
        """Zero source distinct values returns None overlap."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([(0,)]),  # source distinct count = 0
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        overlap = search.compute_overlap(
            target_schema="dbo",
            target_table="Customers",
            target_column="id",
        )

        assert overlap["overlap_count"] is None
        assert overlap["overlap_percentage"] is None

    def test_full_overlap(self):
        """100% overlap when all source values exist in target."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([(50,)]),  # source distinct count
            _mock_result([(50,)]),  # overlap count = all
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        overlap = search.compute_overlap(
            target_schema="dbo",
            target_table="Customers",
            target_column="id",
        )

        assert overlap["overlap_count"] == 50
        assert overlap["overlap_percentage"] == 100.0


# ---------------------------------------------------------------------------
# Result limiting
# ---------------------------------------------------------------------------

class TestResultLimiting:
    """Tests for result limiting and was_limited flag."""

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_default_limit_of_100(self, mock_pk_cls):
        """Default limit is 100."""
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )

        # Create 150 fake candidates to trigger limiting
        from src.models.analysis import FKCandidateData

        all_candidates = []
        for i in range(150):
            all_candidates.append(FKCandidateData(
                source_column="customer_id",
                source_table="Orders",
                source_schema="dbo",
                source_data_type="int",
                target_column=f"col_{i}",
                target_table=f"Table_{i}",
                target_schema="dbo",
                target_data_type="int",
                target_is_primary_key=False,
                target_is_unique=False,
                target_is_nullable=False,
                target_has_index=False,
            ))

        result = search.apply_limit(all_candidates, limit=100)

        assert len(result.candidates) == 100
        assert result.total_found == 150
        assert result.was_limited is True

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_no_limit_when_under_threshold(self, mock_pk_cls):
        """No limiting when results are under the limit."""
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )

        from src.models.analysis import FKCandidateData

        all_candidates = []
        for i in range(5):
            all_candidates.append(FKCandidateData(
                source_column="customer_id",
                source_table="Orders",
                source_schema="dbo",
                source_data_type="int",
                target_column=f"col_{i}",
                target_table=f"Table_{i}",
                target_schema="dbo",
                target_data_type="int",
                target_is_primary_key=False,
                target_is_unique=False,
                target_is_nullable=False,
                target_has_index=False,
            ))

        result = search.apply_limit(all_candidates, limit=100)

        assert len(result.candidates) == 5
        assert result.total_found == 5
        assert result.was_limited is False

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_zero_limit_disables_limiting(self, mock_pk_cls):
        """Limit of 0 means no limit."""
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )

        from src.models.analysis import FKCandidateData

        all_candidates = []
        for i in range(150):
            all_candidates.append(FKCandidateData(
                source_column="customer_id",
                source_table="Orders",
                source_schema="dbo",
                source_data_type="int",
                target_column=f"col_{i}",
                target_table=f"Table_{i}",
                target_schema="dbo",
                target_data_type="int",
                target_is_primary_key=False,
                target_is_unique=False,
                target_is_nullable=False,
                target_has_index=False,
            ))

        result = search.apply_limit(all_candidates, limit=0)

        assert len(result.candidates) == 150
        assert result.total_found == 150
        assert result.was_limited is False


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------

class TestEmptyResults:
    """Tests for empty result scenarios."""

    def test_no_target_tables_returns_empty(self):
        """When no target tables found, returns empty result."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([]),  # no target tables
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        tables = search.get_target_tables()

        assert tables == []

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_no_pk_candidates_returns_empty(self, mock_pk_cls):
        """When target has no PK candidates, returns empty for that table."""
        conn = MagicMock()
        mock_pk_instance = MagicMock()
        mock_pk_instance.find_candidates.return_value = []
        mock_pk_cls.return_value = mock_pk_instance

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        columns = search.get_candidate_columns(
            target_schema="dbo",
            target_table="EmptyTable",
            pk_candidates_only=True,
        )

        assert columns == []


# ---------------------------------------------------------------------------
# Full find_candidates flow
# ---------------------------------------------------------------------------

class TestFindCandidates:
    """Tests for the full find_candidates orchestration method."""

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_full_flow_with_pk_filter(self, mock_pk_cls):
        """Full find_candidates flow with PK filter on."""
        conn = MagicMock()

        # Mock target tables query
        conn.execute.side_effect = [
            # get_target_tables: one table
            _mock_result([("dbo", "Customers")]),
            # get_column_metadata: constraint check
            _mock_result([("PRIMARY KEY",)]),
            # get_column_metadata: index check
            _mock_result([("PK_Customers",)]),
        ]

        # Mock PKDiscovery for target table
        mock_pk_instance = MagicMock()
        mock_pk_instance.find_candidates.return_value = [
            _make_pk_candidate("CustomerID", "int"),
        ]
        mock_pk_cls.return_value = mock_pk_instance

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="CustomerID",
            source_data_type="int",
        )
        result = search.find_candidates(
            pk_candidates_only=True,
            include_overlap=False,
            limit=100,
        )

        assert result.total_found >= 1
        assert len(result.candidates) >= 1
        candidate = result.candidates[0]
        assert candidate.target_table == "Customers"
        assert candidate.target_column == "CustomerID"
        assert candidate.source_column == "CustomerID"

    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_full_flow_with_overlap(self, mock_pk_cls):
        """Full find_candidates flow with overlap enabled."""
        conn = MagicMock()

        conn.execute.side_effect = [
            # get_target_tables
            _mock_result([("dbo", "Customers")]),
            # get_column_metadata: constraint check
            _mock_result([("PRIMARY KEY",)]),
            # get_column_metadata: index check
            _mock_result([("PK_Customers",)]),
            # compute_overlap: source distinct count
            _mock_result([(100,)]),
            # compute_overlap: intersection count
            _mock_result([(95,)]),
        ]

        mock_pk_instance = MagicMock()
        mock_pk_instance.find_candidates.return_value = [
            _make_pk_candidate("CustomerID", "int"),
        ]
        mock_pk_cls.return_value = mock_pk_instance

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="CustomerID",
            source_data_type="int",
        )
        result = search.find_candidates(
            pk_candidates_only=True,
            include_overlap=True,
            limit=100,
        )

        assert len(result.candidates) >= 1
        candidate = result.candidates[0]
        assert candidate.overlap_count == 95
        assert candidate.overlap_percentage == 95.0

    def test_search_scope_description(self):
        """search_scope describes the applied filters."""
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        scope = search.build_search_scope(
            target_schema=None,
            target_tables=None,
            target_table_pattern=None,
            pk_candidates_only=True,
        )

        assert "dbo" in scope
        assert "pk_candidates_only" in scope


# ---------------------------------------------------------------------------
# Inspector shape builder (dialect fixtures live in tests/conftest.py)
# ---------------------------------------------------------------------------

def _build_inspector(
    table_names=None,
    columns=None,
    pk_constraint=None,
    unique_constraints=None,
    indexes=None,
):
    """Create a mock Inspector. Local shape-builder (not a fixture).

    Named to distinguish from the conftest-level ``mock_inspector`` fixture,
    which has a different column shape.
    """
    insp = MagicMock()
    insp.get_table_names.return_value = table_names or []
    insp.get_columns.return_value = columns or []
    insp.get_pk_constraint.return_value = pk_constraint or {
        "constrained_columns": [], "name": None,
    }
    insp.get_unique_constraints.return_value = unique_constraints or []
    insp.get_indexes.return_value = indexes or []
    return insp


# ---------------------------------------------------------------------------
# Inspector-based table discovery
# ---------------------------------------------------------------------------

class TestInspectorTableDiscovery:
    """Tests for Inspector-based table listing (non-MSSQL)."""

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_table_listing_with_target_tables_filter(self, dialect):
        """Inspector-based table listing filters by explicit target_tables."""
        inspector = _build_inspector(
            table_names=["Customers", "Products", "Orders"],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="OrderItems",
            source_column="product_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        tables = search.get_target_tables(
            target_tables=["Customers", "Products"],
        )

        table_names = [t[1] for t in tables]
        assert "Customers" in table_names
        assert "Products" in table_names
        assert "Orders" not in table_names

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_table_listing_with_pattern_filter(self, dialect):
        """Inspector-based table listing filters by pattern."""
        inspector = _build_inspector(
            table_names=["Customers", "Categories", "Products"],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        tables = search.get_target_tables(
            target_table_pattern="C%",
        )

        table_names = [t[1] for t in tables]
        assert "Customers" in table_names
        assert "Categories" in table_names
        assert "Products" not in table_names

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_table_listing_excludes_source(self, dialect):
        """Inspector-based table listing excludes source table."""
        inspector = _build_inspector(
            table_names=["Customers", "Orders", "Products"],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        tables = search.get_target_tables()

        table_names = [t[1] for t in tables]
        assert "Orders" not in table_names
        assert "Customers" in table_names

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_table_listing_sorted(self, dialect):
        """Inspector-based table listing returns sorted results."""
        inspector = _build_inspector(
            table_names=["Zebra", "Apple", "Mango"],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Other",
            source_column="id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        tables = search.get_target_tables()

        table_names = [t[1] for t in tables]
        assert table_names == ["Apple", "Mango", "Zebra"]


# ---------------------------------------------------------------------------
# Dialect-aware metadata collection
# ---------------------------------------------------------------------------

class TestDialectAwareMetadata:
    """Tests for dialect-aware constraint and index metadata."""

    def test_mssql_uses_sys_indexes(self):
        """MSSQL uses sys.indexes for has_index check."""
        conn = MagicMock()
        conn.execute.side_effect = [
            _mock_result([("PRIMARY KEY",)]),  # constraint check
            _mock_result([("idx_pk",)]),        # index check (sys.indexes)
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="dbo",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
        )
        metadata = search.get_column_metadata(
            target_schema="dbo",
            target_table="Customers",
            target_column="id",
            target_data_type="int",
            target_is_nullable=False,
        )

        assert metadata["target_has_index"] is True

    @pytest.mark.dialects('generic')
    def test_generic_uses_inspector_get_indexes(self, dialect):
        """Generic dialect uses Inspector.get_indexes() for has_index."""
        inspector = _build_inspector(
            pk_constraint={"constrained_columns": ["id"], "name": "pk_customers"},
            unique_constraints=[],
            indexes=[
                {"column_names": ["id"], "name": "idx_pk", "unique": True},
                {"column_names": ["email"], "name": "idx_email", "unique": False},
            ],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        metadata = search.get_column_metadata(
            target_schema="public",
            target_table="Customers",
            target_column="id",
            target_data_type="int",
            target_is_nullable=False,
        )

        assert metadata["target_is_primary_key"] is True
        assert metadata["target_has_index"] is True

    @pytest.mark.dialects('databricks')
    def test_databricks_omits_target_has_index(self, dialect):
        """Databricks returns target_has_index=None (supports_indexes=False)."""
        inspector = _build_inspector(
            pk_constraint={"constrained_columns": ["id"], "name": "pk_t"},
            unique_constraints=[],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="main",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        metadata = search.get_column_metadata(
            target_schema="main",
            target_table="Customers",
            target_column="id",
            target_data_type="BIGINT",
            target_is_nullable=False,
        )

        assert metadata["target_has_index"] is None

    def test_fk_candidate_data_to_dict_omits_none_index(self):
        """FKCandidateData.to_dict() omits target_has_index when None."""
        from src.models.analysis import FKCandidateData

        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="Orders",
            source_schema="main",
            source_data_type="int",
            target_column="id",
            target_table="Customers",
            target_schema="main",
            target_data_type="BIGINT",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=None,
        )
        d = candidate.to_dict()

        assert "target_has_index" not in d

    @pytest.mark.dialects('generic')
    def test_generic_inspector_constraints(self, dialect):
        """Generic dialect uses Inspector for constraint checks (target_has_index=True requires supports_indexes)."""
        inspector = _build_inspector(
            pk_constraint={"constrained_columns": [], "name": None},
            unique_constraints=[{"column_names": ["email"], "name": "uq_email"}],
            indexes=[{"column_names": ["email"], "name": "idx_email", "unique": True}],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        metadata = search.get_column_metadata(
            target_schema="public",
            target_table="Customers",
            target_column="email",
            target_data_type="varchar",
            target_is_nullable=False,
        )

        assert metadata["target_is_primary_key"] is False
        assert metadata["target_is_unique"] is True
        assert metadata["target_has_index"] is True


# ---------------------------------------------------------------------------
# Transpiled overlap
# ---------------------------------------------------------------------------

class TestTranspiledOverlap:
    """Tests for SQL transpilation in overlap queries."""

    @pytest.mark.dialects('generic', 'databricks')
    def test_overlap_transpiled_for_non_mssql(self, dialect):
        """INTERSECT query is transpiled for non-MSSQL dialect."""
        # Generic dialect with sqlglot_dialect=None means no transpilation
        # But the code still calls transpile_query (which is a no-op for None)
        inspector = _build_inspector()
        conn = MagicMock()

        conn.execute.side_effect = [
            _mock_result([(100,)]),  # source distinct count
            _mock_result([(85,)]),   # overlap count
        ]

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        overlap = search.compute_overlap(
            target_schema="public",
            target_table="Customers",
            target_column="id",
        )

        assert overlap["overlap_count"] == 85
        assert overlap["overlap_percentage"] == 85.0


# ---------------------------------------------------------------------------
# Inspector-based candidate columns
# ---------------------------------------------------------------------------

class TestInspectorCandidateColumns:
    """Tests for Inspector-based candidate column discovery."""

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_all_columns_non_mssql(self, dialect):
        """Non-MSSQL with pk_candidates_only=False uses Inspector.get_columns()."""
        inspector = _build_inspector(
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
                {"name": "name", "type": MagicMock(__str__=lambda s: "VARCHAR"), "nullable": True},
            ],
        )
        conn = MagicMock()

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        columns = search.get_candidate_columns(
            target_schema="public",
            target_table="Customers",
            pk_candidates_only=False,
        )

        assert len(columns) == 2
        assert columns[0]["column_name"] == "id"
        assert columns[1]["column_name"] == "name"

    @pytest.mark.dialects('generic', 'databricks')
    @patch("src.analysis.fk_candidates.PKDiscovery")
    def test_pk_discovery_receives_dialect_inspector(self, mock_pk_cls, dialect):
        """PKDiscovery constructor receives dialect and inspector."""
        inspector = _build_inspector()
        conn = MagicMock()

        mock_pk_instance = MagicMock()
        mock_pk_instance.find_candidates.return_value = [
            _make_pk_candidate("id", "int"),
        ]
        mock_pk_cls.return_value = mock_pk_instance

        search = FKCandidateSearch(
            connection=conn,
            source_schema="public",
            source_table="Orders",
            source_column="customer_id",
            source_data_type="int",
            dialect=dialect.dialect,
            inspector=inspector,
        )
        search.get_candidate_columns(
            target_schema="public",
            target_table="Customers",
            pk_candidates_only=True,
        )

        mock_pk_cls.assert_called_once_with(
            connection=conn,
            schema_name="public",
            table_name="Customers",
            dialect=dialect.dialect,
            inspector=inspector,
        )
