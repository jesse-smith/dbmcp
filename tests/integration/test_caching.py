"""Integration tests for documentation caching and drift detection.

Tests for DocumentationStorage caching, hash computation, and drift detection - T112.

Fixtures (sample_schemas, sample_tables, sample_columns, sample_declared_fks,
sample_inferred_fks, temp_cache_dir) are provided by tests/integration/conftest.py.
"""

import json

import pytest

from src.cache.storage import DocumentationStorage
from src.models.schema import Table, TableType


class TestCacheExport:
    """Tests for cache export functionality."""

    def test_export_creates_directory_structure(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify export creates proper directory structure."""
        storage = DocumentationStorage(temp_cache_dir)

        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        cache_dir = temp_cache_dir / "test_conn"
        assert cache_dir.exists()
        assert (cache_dir / "overview.md").exists()
        assert (cache_dir / "schemas").exists()
        assert (cache_dir / "tables").exists()
        assert (cache_dir / "relationships.md").exists()
        assert (cache_dir / ".cache_metadata.json").exists()

    def test_export_stores_schema_hash(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify schema hash is stored in metadata."""
        storage = DocumentationStorage(temp_cache_dir)

        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        metadata_path = temp_cache_dir / "test_conn" / ".cache_metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert "schema_hash" in metadata
        assert len(metadata["schema_hash"]) == 64  # SHA-256 hex length


class TestCacheLoad:
    """Tests for cache loading functionality."""

    def test_load_cached_docs_returns_data(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify load_cached_docs returns expected data structure."""
        storage = DocumentationStorage(temp_cache_dir)

        # First export
        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        # Then load
        cached = storage.load_cached_docs("test_conn")

        assert cached["connection_id"] == "test_conn"
        assert cached["database_name"] == "TestDB"
        assert "schemas" in cached
        assert "tables" in cached
        assert "relationships" in cached
        assert "cache_age_days" in cached
        assert "schema_hash" in cached

    def test_load_nonexistent_cache_raises(self, temp_cache_dir):
        """Verify loading nonexistent cache raises ValueError."""
        storage = DocumentationStorage(temp_cache_dir)

        with pytest.raises(ValueError, match="No cached documentation found"):
            storage.load_cached_docs("nonexistent_conn")


class TestSchemaHash:
    """Tests for schema hash computation - drift detection."""

    def test_compute_schema_hash_deterministic(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
    ):
        """Verify same schema produces same hash."""
        storage = DocumentationStorage(temp_cache_dir)

        hash1 = storage.compute_schema_hash(sample_schemas, sample_tables)
        hash2 = storage.compute_schema_hash(sample_schemas, sample_tables)

        assert hash1 == hash2

    def test_compute_schema_hash_different_for_added_table(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
    ):
        """Verify hash changes when table is added."""
        storage = DocumentationStorage(temp_cache_dir)

        hash_before = storage.compute_schema_hash(sample_schemas, sample_tables)

        # Add a new table
        modified_tables = {
            "main": sample_tables["main"] + [
                Table(
                    table_id="main.new_table",
                    schema_id="main",
                    table_name="new_table",
                    table_type=TableType.TABLE,
                    row_count=10,
                    has_primary_key=True,
                ),
            ],
        }

        hash_after = storage.compute_schema_hash(sample_schemas, modified_tables)

        assert hash_before != hash_after

    def test_compute_schema_hash_different_for_removed_table(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
    ):
        """Verify hash changes when table is removed."""
        storage = DocumentationStorage(temp_cache_dir)

        hash_before = storage.compute_schema_hash(sample_schemas, sample_tables)

        # Remove a table
        modified_tables = {
            "main": sample_tables["main"][:2],  # Keep only first 2 tables
        }

        hash_after = storage.compute_schema_hash(sample_schemas, modified_tables)

        assert hash_before != hash_after


class TestDriftDetection:
    """Tests for drift detection between cached and live schema."""

    def test_detect_drift_when_schema_changed(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify drift is detected when schema changes after caching."""
        storage = DocumentationStorage(temp_cache_dir)

        # Export initial schema
        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        # Load cached data and get stored hash
        cached = storage.load_cached_docs("test_conn")
        cached_hash = cached["schema_hash"]

        # Simulate schema change (add table)
        modified_tables = {
            "main": sample_tables["main"] + [
                Table(
                    table_id="main.audit_log",
                    schema_id="main",
                    table_name="audit_log",
                    table_type=TableType.TABLE,
                    row_count=1000,
                    has_primary_key=True,
                ),
            ],
        }

        # Compute new hash
        live_hash = storage.compute_schema_hash(sample_schemas, modified_tables)

        # Verify drift detected
        assert cached_hash != live_hash

    def test_no_drift_when_schema_unchanged(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify no drift when schema hasn't changed."""
        storage = DocumentationStorage(temp_cache_dir)

        # Export initial schema
        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        # Load cached data and get stored hash
        cached = storage.load_cached_docs("test_conn")
        cached_hash = cached["schema_hash"]

        # Compute current hash (same schema)
        live_hash = storage.compute_schema_hash(sample_schemas, sample_tables)

        # Verify no drift
        assert cached_hash == live_hash


class TestCacheAge:
    """Tests for cache age calculation."""

    def test_cache_age_days_calculated(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify cache age is calculated from created_at timestamp."""
        storage = DocumentationStorage(temp_cache_dir)

        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        cached = storage.load_cached_docs("test_conn")

        # Cache was just created, so age should be 0 days
        assert cached["cache_age_days"] == 0


class TestCacheExists:
    """Tests for cache existence checking."""

    def test_cache_exists_returns_true_when_present(
        self,
        temp_cache_dir,
        sample_schemas,
        sample_tables,
        sample_columns,
        sample_declared_fks,
        sample_inferred_fks,
    ):
        """Verify cache_exists returns True after export."""
        storage = DocumentationStorage(temp_cache_dir)

        assert storage.cache_exists("test_conn") is False

        storage.export_documentation(
            connection_id="test_conn",
            database_name="TestDB",
            schemas=sample_schemas,
            tables=sample_tables,
            columns=sample_columns,
            indexes={},
            declared_fks=sample_declared_fks,
            inferred_fks=sample_inferred_fks,
        )

        assert storage.cache_exists("test_conn") is True

    def test_cache_exists_returns_false_when_missing(self, temp_cache_dir):
        """Verify cache_exists returns False for nonexistent connection."""
        storage = DocumentationStorage(temp_cache_dir)
        assert storage.cache_exists("nonexistent") is False
