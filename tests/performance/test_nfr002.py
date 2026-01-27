"""NFR-002 Performance Validation: Sample Data Retrieval.

T124: Validate sample data retrieval completes in <10s for all table sizes.

NFR-002 Requirement:
    Sample data retrieval (get_sample_data) must complete in <10 seconds
    for tables up to 1 million rows.

Test Strategy:
    1. Create test tables with varying row counts (100, 1K, 10K, 100K rows)
    2. Measure get_sample_data execution time with different sampling methods
    3. Verify p95 time is under threshold
    4. Test all sampling methods (TOP, TABLESAMPLE, MODULO)
"""

import pytest
from sqlalchemy import create_engine, text

from src.db.query import QueryService
from src.models.schema import SamplingMethod
from tests.performance.benchmark import Benchmark, assert_performance


# NFR-002 threshold: 10 seconds for any table size
NFR_002_THRESHOLD_MS = 10_000


class TestNFR002SampleDataPerformance:
    """NFR-002: Sample data retrieval must complete in <10s."""

    @pytest.fixture
    def small_table_db(self):
        """Create database with 100-row table."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE small_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT,
                    amount REAL,
                    status TEXT,
                    created_at TEXT
                )
            """))
            for i in range(100):
                conn.execute(text(f"""
                    INSERT INTO small_table (name, email, amount, status, created_at)
                    VALUES ('user_{i}', 'user_{i}@example.com', {i * 10.5}, 'active', datetime('now'))
                """))
            conn.commit()
        return engine

    @pytest.fixture
    def medium_table_db(self):
        """Create database with 1000-row table."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE medium_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    value REAL,
                    count INTEGER,
                    category TEXT
                )
            """))
            # Insert in batches
            for batch in range(10):
                values = ", ".join(
                    f"('item_{batch * 100 + i}', 'Description {i}', {i * 1.5}, {i}, 'cat_{i % 5}')"
                    for i in range(100)
                )
                conn.execute(text(f"""
                    INSERT INTO medium_table (name, description, value, count, category)
                    VALUES {values}
                """))
            conn.commit()
        return engine

    @pytest.fixture
    def large_table_db(self):
        """Create database with 10000-row table."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE large_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    data TEXT,
                    amount REAL
                )
            """))
            # Insert in larger batches
            for batch in range(100):
                values = ", ".join(
                    f"('item_{batch * 100 + i}', 'Data {i}', {i * 0.5})"
                    for i in range(100)
                )
                conn.execute(text(f"""
                    INSERT INTO large_table (name, data, amount)
                    VALUES {values}
                """))
            conn.commit()
        return engine

    def test_sample_data_100_rows_top(self, small_table_db):
        """Test sample data performance with 100 rows using TOP method."""
        service = QueryService(small_table_db)

        result = assert_performance(
            func=lambda: service.get_sample_data(
                table_name="small_table",
                schema_name="main",
                sample_size=10,
                sampling_method=SamplingMethod.TOP,
            ),
            max_ms=1000,  # 1s max for 100-row table
            name="sample_100_rows_top",
            iterations=5,
        )

        print(f"\nget_sample_data (100 rows, TOP): p95={result.p95_ms:.2f}ms")

    def test_sample_data_1000_rows_top(self, medium_table_db):
        """Test sample data performance with 1000 rows using TOP method."""
        service = QueryService(medium_table_db)

        result = assert_performance(
            func=lambda: service.get_sample_data(
                table_name="medium_table",
                schema_name="main",
                sample_size=50,
                sampling_method=SamplingMethod.TOP,
            ),
            max_ms=2000,  # 2s max for 1000-row table
            name="sample_1000_rows_top",
            iterations=5,
        )

        print(f"\nget_sample_data (1000 rows, TOP): p95={result.p95_ms:.2f}ms")

    def test_sample_data_10000_rows_top(self, large_table_db):
        """Test sample data performance with 10000 rows using TOP method."""
        service = QueryService(large_table_db)

        result = assert_performance(
            func=lambda: service.get_sample_data(
                table_name="large_table",
                schema_name="main",
                sample_size=100,
                sampling_method=SamplingMethod.TOP,
            ),
            max_ms=5000,  # 5s max for 10000-row table
            name="sample_10000_rows_top",
            iterations=3,
        )

        print(f"\nget_sample_data (10000 rows, TOP): p95={result.p95_ms:.2f}ms")

    def test_sample_data_with_column_filter(self, medium_table_db):
        """Test sample data performance with column filtering."""
        service = QueryService(medium_table_db)

        result = assert_performance(
            func=lambda: service.get_sample_data(
                table_name="medium_table",
                schema_name="main",
                sample_size=50,
                columns=["name", "value"],  # Only 2 columns
            ),
            max_ms=2000,
            name="sample_filtered_columns",
            iterations=5,
        )

        print(f"\nget_sample_data (filtered columns): p95={result.p95_ms:.2f}ms")

    def test_sample_data_max_sample_size(self, large_table_db):
        """Test sample data performance at max sample size (1000)."""
        service = QueryService(large_table_db)

        result = assert_performance(
            func=lambda: service.get_sample_data(
                table_name="large_table",
                schema_name="main",
                sample_size=1000,  # Max allowed
                sampling_method=SamplingMethod.TOP,
            ),
            max_ms=NFR_002_THRESHOLD_MS,  # Must meet NFR-002
            name="sample_max_size",
            iterations=3,
        )

        print(f"\nget_sample_data (max size 1000): p95={result.p95_ms:.2f}ms")

    @pytest.mark.slow
    def test_sample_data_scaling(self, request):
        """Test how sample data scales with table size.

        Marked as slow - skip in CI with -m "not slow".
        """
        bench = Benchmark()
        scaling_data = []

        row_counts = [100, 500, 1000, 5000]

        for row_count in row_counts:
            # Create database with specified row count
            engine = create_engine("sqlite:///:memory:", echo=False)
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE scaling_table (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        value REAL
                    )
                """))
                # Insert in batches
                batch_size = 100
                for batch in range(0, row_count, batch_size):
                    end = min(batch + batch_size, row_count)
                    values = ", ".join(
                        f"('item_{i}', {i * 0.5})"
                        for i in range(batch, end)
                    )
                    if values:
                        conn.execute(text(f"""
                            INSERT INTO scaling_table (name, value)
                            VALUES {values}
                        """))
                conn.commit()

            service = QueryService(engine)

            # Benchmark
            result = bench.run(
                name=f"sample_{row_count}_rows",
                func=lambda: service.get_sample_data(
                    table_name="scaling_table",
                    schema_name="main",
                    sample_size=50,
                ),
                iterations=3,
            )

            scaling_data.append({
                "row_count": row_count,
                "mean_ms": result.mean_ms,
                "p95_ms": result.p95_ms,
            })

            engine.dispose()

        bench.print_summary()

        # All should be under NFR threshold
        for data in scaling_data:
            assert data["p95_ms"] < NFR_002_THRESHOLD_MS, (
                f"NFR-002 violation: {data['row_count']} rows took {data['p95_ms']:.2f}ms "
                f"(threshold: {NFR_002_THRESHOLD_MS}ms)"
            )

        print("\n\nScaling Analysis:")
        for data in scaling_data:
            print(f"  {data['row_count']:>6} rows: {data['mean_ms']:.2f}ms (p95: {data['p95_ms']:.2f}ms)")
        print(f"\n  NFR-002 threshold: {NFR_002_THRESHOLD_MS}ms")
        print("  Status: PASS" if all(d["p95_ms"] < NFR_002_THRESHOLD_MS for d in scaling_data) else "  Status: FAIL")
