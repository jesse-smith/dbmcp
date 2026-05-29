"""Unit tests for PKDiscovery class.

Tests PK candidate discovery including constraint-backed detection,
structural candidate analysis, and type filtering.
"""

from unittest.mock import MagicMock

import pytest
import sqlglot

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


# ---------------------------------------------------------------------------
# PK Inspector shape builder (dialect fixtures come from tests/conftest.py)
# ---------------------------------------------------------------------------

def _mock_inspector_for_pk(
    pk_columns=None,
    unique_constraints=None,
    columns=None,
    pk_name=None,
):
    """Create a mock Inspector with PK/UNIQUE/columns data."""
    insp = MagicMock()

    pk_info = {"constrained_columns": pk_columns or [], "name": pk_name}
    insp.get_pk_constraint.return_value = pk_info

    insp.get_unique_constraints.return_value = unique_constraints or []

    insp.get_columns.return_value = columns or []

    return insp


# ---------------------------------------------------------------------------
# Inspector-based constraint discovery
# ---------------------------------------------------------------------------

class TestInspectorConstraintDiscovery:
    """Tests for Inspector-based PK/UNIQUE constraint discovery (non-MSSQL)."""

    @pytest.mark.dialects('generic', 'databricks')
    def test_pk_discovered_via_inspector(self, dialect):
        """PK discovered via Inspector for non-MSSQL dialects (generic/databricks)."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
                {"name": "name", "type": MagicMock(__str__=lambda s: "VARCHAR"), "nullable": True},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert len(candidates) == 1
        assert candidates[0].column_name == "id"
        assert candidates[0].data_type == "INTEGER"
        assert candidates[0].is_constraint_backed is True
        assert candidates[0].constraint_type == "PRIMARY KEY"
        assert candidates[0].is_unique is True
        assert candidates[0].is_non_null is True

    @pytest.mark.dialects('generic', 'databricks')
    def test_unique_discovered_via_inspector(self, dialect):
        """UNIQUE constraint discovered via Inspector for non-MSSQL dialects."""
        inspector = _mock_inspector_for_pk(
            pk_columns=[],
            unique_constraints=[{"column_names": ["email"], "name": "uq_email"}],
            columns=[
                {"name": "email", "type": MagicMock(__str__=lambda s: "VARCHAR"), "nullable": True},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert len(candidates) == 1
        assert candidates[0].column_name == "email"
        assert candidates[0].is_constraint_backed is True
        assert candidates[0].constraint_type == "UNIQUE"
        assert candidates[0].is_non_null is False

    @pytest.mark.dialects('databricks')
    def test_databricks_constraints_have_enforced_false(self, dialect):
        """Databricks constraints have constraint_enforced=False."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            unique_constraints=[{"column_names": ["code"], "name": "uq_code"}],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "BIGINT"), "nullable": False},
                {"name": "code", "type": MagicMock(__str__=lambda s: "STRING"), "nullable": True},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "main", "products", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert len(candidates) == 2
        for c in candidates:
            assert c.constraint_enforced is False

    @pytest.mark.dialects('generic')
    def test_generic_constraints_have_enforced_true(self, dialect):
        """Generic dialect constraints have constraint_enforced=True."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert len(candidates) == 1
        assert candidates[0].constraint_enforced is True

    @pytest.mark.dialects('generic', 'databricks')
    def test_inspector_column_listing_for_structural(self, dialect):
        """Inspector-based column listing works for structural candidates."""
        inspector = _mock_inspector_for_pk(
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
                {"name": "status", "type": MagicMock(__str__=lambda s: "VARCHAR"), "nullable": True},
            ],
        )
        conn = MagicMock()

        # uniqueness check for "id" (only non-null int column)
        uniqueness_row = MagicMock()
        uniqueness_row.__getitem__ = lambda self, idx: [100, 100][idx]
        conn.execute.return_value = _mock_result([uniqueness_row])

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_structural_candidates(
            type_filter=[],
            exclude_columns=set(),
        )

        # "id" passes (non-null, unique), "status" excluded (nullable)
        assert len(candidates) == 1
        assert candidates[0].column_name == "id"

    @pytest.mark.dialects('generic', 'databricks')
    def test_type_filter_with_inspector_string_types(self, dialect):
        """Type filter works with SQLAlchemy type string representation."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        # Filter for "integer" should match "INTEGER" (case-insensitive)
        candidates = discovery.get_constraint_candidates(type_filter=["integer"])

        assert len(candidates) == 1
        assert candidates[0].is_pk_type is True

    @pytest.mark.dialects('generic', 'databricks')
    def test_type_filter_excludes_non_matching_inspector(self, dialect):
        """Type filter correctly excludes non-matching types from Inspector."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(conn, "public", "users", dialect=dialect.dialect, inspector=inspector)
        candidates = discovery.get_constraint_candidates(type_filter=["varchar"])

        assert len(candidates) == 1
        assert candidates[0].is_pk_type is False


# ---------------------------------------------------------------------------
# Dialect backward compatibility
# ---------------------------------------------------------------------------

class TestDialectBackwardCompat:
    """Tests for backward compat: dialect=None uses INFORMATION_SCHEMA."""

    def test_dialect_none_uses_information_schema(self):
        """dialect=None uses INFORMATION_SCHEMA queries (existing behavior)."""
        conn = MagicMock()
        pk_rows = [("order_id", "int", "PRIMARY KEY")]
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        # Verify it used connection.execute (INFORMATION_SCHEMA path)
        assert conn.execute.call_count == 2
        assert len(candidates) == 1
        assert candidates[0].column_name == "order_id"

    @pytest.mark.dialects('mssql')
    def test_mssql_dialect_uses_information_schema(self, dialect):
        """MSSQL dialect uses INFORMATION_SCHEMA queries."""
        conn = MagicMock()
        pk_rows = [("order_id", "int", "PRIMARY KEY")]
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders", dialect=dialect.dialect)
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert conn.execute.call_count == 2
        assert len(candidates) == 1

    def test_constraint_enforced_none_for_mssql(self):
        """constraint_enforced is None for MSSQL (backward compat)."""
        conn = MagicMock()
        pk_rows = [("order_id", "int", "PRIMARY KEY")]
        uq_rows = []
        conn.execute.side_effect = [
            _mock_result(pk_rows),
            _mock_result(uq_rows),
        ]

        discovery = PKDiscovery(conn, "dbo", "orders")
        candidates = discovery.get_constraint_candidates(type_filter=DEFAULT_PK_TYPE_FILTER)

        assert candidates[0].constraint_enforced is None


# ---------------------------------------------------------------------------
# Cross-catalog PK discovery (IDENT-08, CR-02)
# ---------------------------------------------------------------------------

class _CatalogDiscriminatingConnection:
    """Fake connection whose constraint/column reads only return rows when the
    executed SQL carries the requested catalog in its 3-part name.

    Models the CR-02 silent mis-targeting: a query that omits the catalog (or
    targets the connection's default catalog) is a false negative -- it returns
    no rows -- whereas a query qualified to the requested catalog returns the
    real metadata. Also asserts no ``USE CATALOG`` is ever emitted (the
    cross-catalog path must be stateless, T-15.1-04).
    """

    def __init__(self, expected_catalog: str, schema: str, table: str):
        self.expected_catalog = expected_catalog
        self.schema = schema
        self.table = table
        self.executed_sql: list[str] = []

    def _carries_catalog(self, sql: str) -> bool:
        # Match the catalog segment regardless of backtick/bracket/bare quoting.
        return self.expected_catalog in sql

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)

        # Stateless invariant: never mutate the session's active catalog.
        assert "USE CATALOG" not in sql.upper(), (
            f"cross-catalog path must not emit USE CATALOG; got: {sql}"
        )

        targets_catalog = self._carries_catalog(sql)
        upper = sql.upper()

        # PK / constraint reads (information_schema.table_constraints or
        # key_column_usage). Return a PK row only when catalog-qualified.
        if "TABLE_CONSTRAINTS" in upper or "KEY_COLUMN_USAGE" in upper:
            rows = (
                [("order_id", "int", "PRIMARY KEY")] if targets_catalog else []
            )
            return _mock_result(rows)

        # Nullability reflection (information_schema.columns, NOT constraints).
        # Reflects the table's columns with their declared is_nullable.
        if "INFORMATION_SCHEMA" in upper and ".COLUMNS" in upper:
            rows = (
                [("order_id", "NO"), ("patient_id", "YES")]
                if targets_catalog
                else []
            )
            return _mock_result(rows)

        # Anything else (uniqueness probes, DESCRIBE, etc.): no rows.
        return _mock_result([])


def _make_databricks_dialect():
    """Minimal Databricks dialect stub (name + backtick quoting + transpile)."""
    dialect = MagicMock()
    type(dialect).name = type("P", (), {"__get__": lambda *_: "databricks"})()
    return dialect


class TestCrossCatalogPK:
    """PKDiscovery threads an explicit catalog into its metadata reads."""

    @pytest.mark.dialects('databricks')
    def test_cross_catalog_pk_targets_requested_catalog(self, dialect):
        """With catalog set, constraint reads target that catalog (rows returned).

        Without the catalog the same fake returns [] -- the CR-02 false negative.
        """
        inspector = _mock_inspector_for_pk(columns=[])
        conn = _CatalogDiscriminatingConnection("cerner_src", "dbo", "orders")

        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=inspector,
            catalog="cerner_src",
        )
        candidates = discovery.get_constraint_candidates(type_filter=[])

        # Catalog reached the SQL -> the discriminating fake returned the PK row.
        assert len(candidates) >= 1
        assert any(c.column_name == "order_id" for c in candidates)

    @pytest.mark.dialects('databricks')
    def test_cross_catalog_without_catalog_is_false_negative(self, dialect):
        """Same fake, no catalog -> no rows (proves the fake discriminates)."""
        inspector = _mock_inspector_for_pk(columns=[])
        conn = _CatalogDiscriminatingConnection("cerner_src", "dbo", "orders")

        # No catalog: Inspector path is used, which does not query the fake's
        # information_schema, so the PK row is never surfaced.
        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=inspector,
        )
        candidates = discovery.get_constraint_candidates(type_filter=[])

        assert candidates == []

    @pytest.mark.dialects('databricks')
    def test_qualified_table_three_part(self, dialect):
        """_qualified_table is 3-part TSQL brackets, transpiling to backticks."""
        discovery = PKDiscovery(
            MagicMock(), "sch", "tbl",
            dialect=dialect.dialect, inspector=MagicMock(),
            catalog="cat",
        )

        assert discovery._qualified_table == "[cat].[sch].[tbl]"

        transpiled = sqlglot.transpile(
            f"SELECT * FROM {discovery._qualified_table}",
            read="tsql", write="databricks",
        )[0]
        assert "`cat`.`sch`.`tbl`" in transpiled

    @pytest.mark.dialects('databricks')
    def test_no_use_catalog(self, dialect):
        """No USE CATALOG is emitted on the cross-catalog branch."""
        inspector = _mock_inspector_for_pk(columns=[])
        conn = _CatalogDiscriminatingConnection("cerner_src", "dbo", "orders")

        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=inspector,
            catalog="cerner_src",
        )
        # The fake asserts internally, but assert explicitly too for clarity.
        discovery.get_constraint_candidates(type_filter=[])

        for sql in conn.executed_sql:
            assert "USE CATALOG" not in sql.upper()

    @pytest.mark.dialects('databricks')
    def test_default_path_unchanged(self, dialect):
        """catalog=None still routes through the Inspector (no reflector use)."""
        inspector = _mock_inspector_for_pk(
            pk_columns=["id"],
            columns=[
                {"name": "id", "type": MagicMock(__str__=lambda s: "BIGINT"), "nullable": False},
            ],
        )
        conn = MagicMock()

        discovery = PKDiscovery(
            conn, "main", "products",
            dialect=dialect.dialect, inspector=inspector,
        )
        candidates = discovery.get_constraint_candidates(type_filter=[])

        # Inspector still consulted for columns + PK constraint.
        inspector.get_columns.assert_called()
        inspector.get_pk_constraint.assert_called()
        assert len(candidates) == 1
        assert candidates[0].column_name == "id"


# ---------------------------------------------------------------------------
# WR-03: reflect-and-report nullability + probe-only structural gate
# ---------------------------------------------------------------------------


class _WR03ReflectingConnection:
    """Cross-catalog fake: DESCRIBE returns columns, information_schema.columns
    returns declared nullability, and the uniqueness probe reports the column
    unique. Lets us assert the probe-only structural gate on a declared-nullable
    column (the all-nullable-table regression guard)."""

    def __init__(self, columns, nullability, unique=True):
        # columns: list[(name, data_type)]; nullability: {name: "YES"/"NO"}
        self.columns = columns
        self.nullability = nullability
        self.unique = unique
        self.executed_sql: list[str] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)
        assert "USE CATALOG" not in sql.upper()
        upper = sql.upper()

        if "DESCRIBE TABLE" in upper:
            return _mock_result(self.columns)
        if "INFORMATION_SCHEMA" in upper and ".COLUMNS" in upper:
            return _mock_result(
                [(name, self.nullability[name]) for name, _ in self.columns]
            )
        if "COUNT(DISTINCT" in upper or "COUNT (DISTINCT" in upper:
            # (distinct_count, total_non_null): unique iff equal and > 0.
            return _mock_result([(5, 5)] if self.unique else [(3, 5)])
        return _mock_result([])


class TestWR03NullabilityReflection:
    """PK reflection layer reports reflected nullability; the structural gate
    remains probe-only on the cross-catalog branch (WR-03)."""

    @pytest.mark.dialects("databricks")
    def test_list_all_columns_reports_reflected_nullability(self, dialect):
        """_list_all_columns returns the REFLECTED is_nullable, not a fabricated
        constant: declared YES -> True, declared NO -> False."""
        conn = _WR03ReflectingConnection(
            columns=[("order_id", "int"), ("patient_id", "int")],
            nullability={"order_id": "NO", "patient_id": "YES"},
        )
        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=MagicMock(),
            catalog="cerner_src",
        )

        rows = discovery._list_all_columns()

        by_name = {name: nullable for name, _dt, nullable in rows}
        assert by_name == {"order_id": False, "patient_id": True}

    @pytest.mark.dialects("databricks")
    def test_declared_nullable_probe_unique_still_structural_candidate(self, dialect):
        """REGRESSION GUARD: a column declared is_nullable=YES whose uniqueness
        probe returns True STILL surfaces as a structural PK candidate with
        is_non_null=True (declared nullability must NOT reach the gate)."""
        conn = _WR03ReflectingConnection(
            columns=[("patient_id", "int")],
            nullability={"patient_id": "YES"},  # declared nullable
            unique=True,                          # but empirically unique
        )
        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=MagicMock(),
            catalog="cerner_src",
        )

        candidates = discovery.get_structural_candidates(
            type_filter=[], exclude_columns=set()
        )

        assert len(candidates) == 1
        assert candidates[0].column_name == "patient_id"
        assert candidates[0].is_non_null is True
        assert candidates[0].is_constraint_backed is False

    @pytest.mark.dialects("databricks")
    def test_declared_nullable_probe_nonunique_excluded(self, dialect):
        """A declared-nullable column that is NOT unique is excluded by the
        probe (the probe is the sole structural gate)."""
        conn = _WR03ReflectingConnection(
            columns=[("patient_id", "int")],
            nullability={"patient_id": "YES"},
            unique=False,  # probe fails -> not a structural candidate
        )
        discovery = PKDiscovery(
            conn, "dbo", "orders",
            dialect=dialect.dialect, inspector=MagicMock(),
            catalog="cerner_src",
        )

        candidates = discovery.get_structural_candidates(
            type_filter=[], exclude_columns=set()
        )

        assert candidates == []


class TestWR03StructuralGateDefaultPathUnchanged:
    """The Inspector / default-catalog structural gate still excludes columns
    declared nullable (no behavioral change off the cross-catalog branch)."""

    def test_inspector_nullable_column_excluded(self):
        """catalog=None Inspector path: a nullable column is excluded from
        structural candidacy exactly as before."""
        inspector = MagicMock()
        inspector.get_columns.return_value = [
            {"name": "maybe", "type": MagicMock(__str__=lambda s: "int"),
             "nullable": True},
        ]
        conn = MagicMock()
        # Uniqueness probe would say unique, but the nullable gate excludes first.
        conn.execute.return_value = _mock_result([(5, 5)])

        discovery = PKDiscovery(conn, "dbo", "orders", inspector=inspector)

        candidates = discovery.get_structural_candidates(
            type_filter=[], exclude_columns=set()
        )

        assert candidates == []
