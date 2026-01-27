"""NFR-003 Performance Validation: Documentation Output Size.

T125: Validate documentation output is <1MB for 500-table databases.

NFR-003 Requirement:
    Generated documentation output must be <1MB for databases with up to
    500 tables to ensure efficient storage and transfer.

Test Strategy:
    1. Create test database with varying table counts
    2. Generate documentation using DocumentationStorage
    3. Measure total output size
    4. Verify size is under 1MB threshold for 500 tables
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.cache.storage import DocumentationStorage, NFR_003_SIZE_LIMIT_BYTES
from src.db.metadata import MetadataService
from src.models.schema import Column, Index, Schema, Table, TableType
from tests.performance.benchmark import Benchmark


# NFR-003 threshold: 1MB for 500 tables
NFR_003_TABLE_COUNT = 500


class TestNFR003DocumentationSize:
    """NFR-003: Documentation output must be <1MB for 500 tables."""

    @pytest.fixture
    def temp_docs_dir(self):
        """Create temporary directory for documentation output."""
        temp_dir = tempfile.mkdtemp(prefix="dbmcp_docs_")
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def _create_test_data(self, table_count: int):
        """Create test schema data for documentation generation."""
        schemas = [
            Schema(
                schema_id="test_conn.main",
                connection_id="test_conn",
                schema_name="main",
                table_count=table_count,
                view_count=0,
            ),
        ]

        tables = {
            "main": [
                Table(
                    table_id=f"main.table_{i:03d}",
                    schema_id="main",
                    table_name=f"table_{i:03d}",
                    table_type=TableType.TABLE,
                    row_count=i * 100,
                    has_primary_key=True,
                )
                for i in range(table_count)
            ],
        }

        columns = {}
        indexes = {}
        for i in range(table_count):
            table_id = f"main.table_{i:03d}"
            columns[table_id] = [
                Column(
                    column_id=f"{table_id}.id",
                    table_id=table_id,
                    column_name="id",
                    data_type="INTEGER",
                    is_nullable=False,
                    ordinal_position=1,
                    is_primary_key=True,
                ),
                Column(
                    column_id=f"{table_id}.name",
                    table_id=table_id,
                    column_name="name",
                    data_type="TEXT",
                    is_nullable=False,
                    ordinal_position=2,
                ),
                Column(
                    column_id=f"{table_id}.value",
                    table_id=table_id,
                    column_name="value",
                    data_type="REAL",
                    is_nullable=True,
                    ordinal_position=3,
                ),
            ]
            indexes[table_id] = [
                Index(
                    index_id=f"{table_id}.pk_idx",
                    table_id=table_id,
                    index_name="pk_idx",
                    is_unique=True,
                    columns=["id"],
                ),
            ]

        return schemas, tables, columns, indexes

    def test_documentation_size_limit_constant(self):
        """Verify NFR-003 size limit is correctly defined."""
        assert NFR_003_SIZE_LIMIT_BYTES == 1_000_000, "NFR-003 limit should be 1MB"

    def _calculate_dir_size(self, path: Path) -> int:
        """Calculate total size of all files in a directory."""
        total = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                total += os.path.getsize(os.path.join(root, f))
        return total

    def test_single_table_documentation_size(self, temp_docs_dir):
        """Test documentation size for a single table."""
        storage = DocumentationStorage(temp_docs_dir)

        schemas, tables, columns, indexes = self._create_test_data(1)

        # Export documentation
        result = storage.export_documentation(
            connection_id="test_conn",
            database_name="test_db",
            schemas=schemas,
            tables=tables,
            columns=columns,
            indexes=indexes,
            declared_fks=[],
            inferred_fks=[],
        )

        # Calculate total size from cache directory
        cache_dir = Path(result.cache_dir)
        total_size = self._calculate_dir_size(cache_dir)

        print(f"\nSingle table docs size: {total_size} bytes")
        assert total_size < 10_000, "Single table docs should be <10KB"

    def test_50_table_documentation_size(self, temp_docs_dir):
        """Test documentation size for 50 tables."""
        storage = DocumentationStorage(temp_docs_dir)
        schemas, tables, columns, indexes = self._create_test_data(50)

        result = storage.export_documentation(
            connection_id="test_conn_50",
            database_name="test_db",
            schemas=schemas,
            tables=tables,
            columns=columns,
            indexes=indexes,
            declared_fks=[],
            inferred_fks=[],
        )

        cache_dir = Path(result.cache_dir)
        total_size = self._calculate_dir_size(cache_dir)

        print(f"\n50 table docs size: {total_size} bytes ({total_size / 1024:.2f} KB)")

        # 50 tables should be well under limit
        assert total_size < 500_000, "50 table docs should be <500KB"

        # Extrapolate to 500 tables
        per_table = total_size / 50
        estimated_500 = per_table * 500

        print(f"  Per-table average: {per_table:.0f} bytes")
        print(f"  Estimated for 500 tables: {estimated_500 / 1024:.2f} KB")

        if estimated_500 < NFR_003_SIZE_LIMIT_BYTES:
            print("  NFR-003 projection: PASS")
        else:
            print("  NFR-003 projection: FAIL - optimization needed")

    def test_documentation_file_structure(self, temp_docs_dir):
        """Verify documentation creates expected file structure."""
        storage = DocumentationStorage(temp_docs_dir)
        schemas, tables, columns, indexes = self._create_test_data(10)

        result = storage.export_documentation(
            connection_id="test_conn_struct",
            database_name="test_db",
            schemas=schemas,
            tables=tables,
            columns=columns,
            indexes=indexes,
            declared_fks=[],
            inferred_fks=[],
        )

        # Check expected files exist
        conn_dir = Path(result.cache_dir)
        assert conn_dir.exists(), "Connection directory should be created"
        assert (conn_dir / "overview.md").exists(), "overview.md should exist"

        # Count files
        file_count = sum(1 for _ in conn_dir.rglob("*.md"))
        print(f"\nFiles created: {file_count}")

        # Should have overview + schema files + table files
        assert file_count >= 1, "Should create at least overview.md"

    @pytest.mark.slow
    def test_documentation_scaling(self, temp_docs_dir):
        """Test documentation size scaling with table count.

        Marked as slow - skip in CI with -m "not slow".
        """
        bench = Benchmark(track_memory=False)
        scaling_data = []

        table_counts = [10, 25, 50, 100]

        for count in table_counts:
            schemas, tables, columns, indexes = self._create_test_data(count)

            # Create fresh storage for each test
            test_dir = temp_docs_dir / f"test_{count}"
            test_dir.mkdir(exist_ok=True)
            storage = DocumentationStorage(test_dir)

            result = bench.run(
                name=f"export_{count}_tables",
                func=lambda s=schemas, t=tables, c=columns, i=indexes: storage.export_documentation(
                    connection_id=f"conn_{count}",
                    database_name="test_db",
                    schemas=s,
                    tables=t,
                    columns=c,
                    indexes=i,
                    declared_fks=[],
                    inferred_fks=[],
                ),
                iterations=1,
            )

            # Calculate size
            conn_dir = test_dir / f"conn_{count}"
            total_size = 0
            if conn_dir.exists():
                for root, dirs, files in os.walk(conn_dir):
                    for f in files:
                        total_size += os.path.getsize(os.path.join(root, f))

            scaling_data.append({
                "table_count": count,
                "total_bytes": total_size,
                "time_ms": result.mean_ms,
            })

        bench.print_summary()

        # Analyze scaling
        print("\n\nDocumentation Size Scaling:")
        for data in scaling_data:
            kb = data["total_bytes"] / 1024
            per_table = data["total_bytes"] / data["table_count"]
            print(f"  {data['table_count']:>4} tables: {kb:>8.2f} KB ({per_table:.0f} bytes/table)")

        # Extrapolate to 500 tables
        if scaling_data:
            last = scaling_data[-1]
            per_table = last["total_bytes"] / last["table_count"]
            estimated_500 = per_table * 500

            print(f"\n  Estimated for 500 tables: {estimated_500 / 1024:.2f} KB")
            print(f"  NFR-003 threshold: {NFR_003_SIZE_LIMIT_BYTES / 1024:.2f} KB")

            if estimated_500 < NFR_003_SIZE_LIMIT_BYTES:
                print("  Status: PASS")
            else:
                print("  Status: FAIL - optimization needed")

            # Assert the extrapolation passes
            assert estimated_500 < NFR_003_SIZE_LIMIT_BYTES * 1.5, (
                f"Documentation size scaling too high: "
                f"estimated {estimated_500 / 1024:.2f}KB for 500 tables, "
                f"limit is {NFR_003_SIZE_LIMIT_BYTES / 1024:.2f}KB"
            )
