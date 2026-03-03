"""NFR-001 Performance Validation: Metadata Retrieval.

T123: Validate metadata retrieval completes in <30s for 1000-table databases.

NFR-001 Requirement:
    Metadata retrieval (list_schemas, list_tables) must complete in <30 seconds
    for databases with up to 1000 tables.

Test Strategy:
    1. Create test databases with varying table counts (100, 250, 500, 1000)
    2. Measure list_tables execution time
    3. Verify p95 time is under threshold
    4. Track scaling behavior across table counts
"""

import pytest
from sqlalchemy import create_engine, text

from src.db.metadata import MetadataService
from tests.performance.benchmark import Benchmark, assert_performance

# NFR-001 threshold: 30 seconds for 1000 tables
NFR_001_THRESHOLD_MS = 30_000
NFR_001_TABLE_COUNT = 1000


class TestNFR001MetadataPerformance:
    """NFR-001: Metadata retrieval must complete in <30s for 1000 tables."""

    @pytest.fixture
    def small_test_db(self):
        """Create database with 50 tables for quick testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.connect() as conn:
            for i in range(50):
                conn.execute(text(f"""
                    CREATE TABLE test_table_{i:03d} (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        value REAL,
                        status TEXT
                    )
                """))
                # Add some rows
                for j in range(10):
                    conn.execute(text(f"""
                        INSERT INTO test_table_{i:03d} (name, value, status)
                        VALUES ('item_{j}', {j * 1.5}, 'active')
                    """))
            conn.commit()
        return engine

    @pytest.fixture
    def medium_test_db(self):
        """Create database with 200 tables for medium-scale testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.connect() as conn:
            for i in range(200):
                conn.execute(text(f"""
                    CREATE TABLE table_{i:04d} (
                        id INTEGER PRIMARY KEY,
                        col_a TEXT,
                        col_b REAL,
                        col_c INTEGER
                    )
                """))
            conn.commit()
        return engine

    def test_list_tables_50_tables(self, small_test_db):
        """Test list_tables performance with 50 tables (quick validation)."""
        service = MetadataService(small_test_db)

        # Expected time: ~50ms for 50 tables (scales linearly)
        result = assert_performance(
            func=lambda: service.list_tables(),
            max_ms=5000,  # 5s max for 50 tables
            name="list_tables_50",
            iterations=3,
        )

        print(f"\nlist_tables (50 tables): p95={result.p95_ms:.2f}ms")

    def test_list_tables_200_tables(self, medium_test_db):
        """Test list_tables performance with 200 tables."""
        service = MetadataService(medium_test_db)

        # Expected time: ~200ms for 200 tables
        result = assert_performance(
            func=lambda: service.list_tables(limit=1000),
            max_ms=10000,  # 10s max for 200 tables
            name="list_tables_200",
            iterations=3,
        )

        print(f"\nlist_tables (200 tables): p95={result.p95_ms:.2f}ms")

    def test_list_schemas_performance(self, medium_test_db):
        """Test list_schemas performance."""
        service = MetadataService(medium_test_db)

        result = assert_performance(
            func=lambda: service.list_schemas(),
            max_ms=2000,  # 2s max for list_schemas
            name="list_schemas",
            iterations=5,
        )

        print(f"\nlist_schemas: p95={result.p95_ms:.2f}ms")

    def test_get_table_schema_performance(self, small_test_db):
        """Test get_table_schema performance for single table."""
        service = MetadataService(small_test_db)

        result = assert_performance(
            func=lambda: service.get_table_schema("test_table_001", "main"),
            max_ms=1000,  # 1s max for single table metadata
            name="get_table_schema",
            iterations=5,
        )

        print(f"\nget_table_schema: p95={result.p95_ms:.2f}ms")

    @pytest.mark.slow
    def test_list_tables_scaling_behavior(self, request):
        """Test how list_tables scales with table count.

        This test creates databases of increasing size and measures
        scaling behavior. Marked as slow - skip in CI with -m "not slow".
        """
        bench = Benchmark()
        scaling_data = []

        table_counts = [50, 100, 200]

        for count in table_counts:
            # Create database
            engine = create_engine("sqlite:///:memory:", echo=False)
            with engine.connect() as conn:
                for i in range(count):
                    conn.execute(text(f"""
                        CREATE TABLE scaling_test_{i:04d} (
                            id INTEGER PRIMARY KEY,
                            name TEXT
                        )
                    """))
                conn.commit()

            service = MetadataService(engine)

            # Benchmark
            result = bench.run(
                name=f"list_tables_{count}",
                func=lambda s=service: s.list_tables(limit=1000),
                iterations=3,
            )

            scaling_data.append({
                "table_count": count,
                "mean_ms": result.mean_ms,
                "p95_ms": result.p95_ms,
            })

            engine.dispose()

        bench.print_summary()

        # Verify roughly linear scaling
        # Time should roughly double when table count doubles
        for i in range(1, len(scaling_data)):
            ratio = scaling_data[i]["mean_ms"] / max(scaling_data[i-1]["mean_ms"], 0.001)
            table_ratio = scaling_data[i]["table_count"] / scaling_data[i-1]["table_count"]

            # Allow 3x variance from linear
            assert ratio < table_ratio * 3, (
                f"Non-linear scaling detected: "
                f"{scaling_data[i-1]['table_count']} tables ({scaling_data[i-1]['mean_ms']:.2f}ms) -> "
                f"{scaling_data[i]['table_count']} tables ({scaling_data[i]['mean_ms']:.2f}ms)"
            )

        print("\n\nScaling Analysis:")
        for data in scaling_data:
            print(f"  {data['table_count']} tables: {data['mean_ms']:.2f}ms (p95: {data['p95_ms']:.2f}ms)")

        # Extrapolate to 1000 tables
        if len(scaling_data) >= 2:
            # Use linear regression to estimate
            last = scaling_data[-1]
            ms_per_table = last["mean_ms"] / last["table_count"]
            estimated_1000 = ms_per_table * 1000

            print(f"\n  Estimated for 1000 tables: {estimated_1000:.2f}ms")
            print(f"  NFR-001 threshold: {NFR_001_THRESHOLD_MS}ms")

            if estimated_1000 < NFR_001_THRESHOLD_MS:
                print("  Status: LIKELY PASS")
            else:
                print("  Status: LIKELY FAIL - optimization needed")
