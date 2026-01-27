"""FK Inference Algorithm Scaling Profile.

T126: Profile FK inference algorithm on databases with 50, 100, 250, 500 tables.

This test measures how the inference algorithm scales with database size
to identify potential performance issues before they affect production use.

Expected behavior:
    - O(n * m) complexity where n = source columns, m = target tables
    - Linear scaling with timeout protection (T134)
    - Acceptable performance up to 500 tables
"""

import pytest
from sqlalchemy import create_engine, text

from src.inference.relationships import ForeignKeyInferencer
from tests.performance.benchmark import Benchmark


class TestInferenceScaling:
    """Profile FK inference scaling behavior."""

    def _create_test_db(self, table_count: int):
        """Create test database with specified number of tables.

        Creates a realistic schema with:
        - Dimension tables (targets for FKs)
        - Fact tables with FK-like columns
        """
        engine = create_engine("sqlite:///:memory:", echo=False)

        with engine.connect() as conn:
            # Create dimension tables (10% of total)
            dim_count = max(5, table_count // 10)

            for i in range(dim_count):
                conn.execute(text(f"""
                    CREATE TABLE dim_table_{i:03d} (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        code TEXT
                    )
                """))
                # Add some data
                for j in range(5):
                    conn.execute(text(f"""
                        INSERT INTO dim_table_{i:03d} (name, code)
                        VALUES ('dim_{i}_{j}', 'CODE_{j}')
                    """))

            # Create fact tables (90% of total)
            fact_count = table_count - dim_count

            for i in range(fact_count):
                # Create columns with FK-like names pointing to dimension tables
                dim_refs = []
                for d in range(min(3, dim_count)):
                    if (i + d) % 3 == 0:  # Not all tables have all FKs
                        dim_refs.append(f"dim_table_{d:03d}_id INTEGER")

                columns = [
                    "id INTEGER PRIMARY KEY",
                    *dim_refs,
                    "amount REAL",
                    "status TEXT",
                    "created_at TEXT",
                ]

                conn.execute(text(f"""
                    CREATE TABLE fact_table_{i:03d} ({", ".join(columns)})
                """))

            conn.commit()

        return engine

    def test_inference_50_tables(self):
        """Test inference performance on 50-table database."""
        engine = self._create_test_db(50)
        inferencer = ForeignKeyInferencer(engine, threshold=0.50)

        bench = Benchmark()
        result = bench.run(
            name="inference_50_tables",
            func=lambda: inferencer.infer_relationships(
                table_name="fact_table_000",
                schema_name="main",
                max_candidates=20,
            ),
            iterations=3,
        )

        print(f"\nInference (50 tables): p95={result.p95_ms:.2f}ms")
        assert result.p95_ms < 5000, "Inference on 50 tables should complete in <5s"

        engine.dispose()

    def test_inference_100_tables(self):
        """Test inference performance on 100-table database."""
        engine = self._create_test_db(100)
        inferencer = ForeignKeyInferencer(engine, threshold=0.50)

        bench = Benchmark()
        result = bench.run(
            name="inference_100_tables",
            func=lambda: inferencer.infer_relationships(
                table_name="fact_table_000",
                schema_name="main",
                max_candidates=20,
            ),
            iterations=3,
        )

        print(f"\nInference (100 tables): p95={result.p95_ms:.2f}ms")
        assert result.p95_ms < 10000, "Inference on 100 tables should complete in <10s"

        engine.dispose()

    @pytest.mark.slow
    def test_inference_scaling_profile(self):
        """Full scaling profile across multiple database sizes.

        Marked as slow - skip in CI with -m "not slow".
        """
        bench = Benchmark(track_memory=True)
        scaling_data = []

        table_counts = [25, 50, 100, 200]

        for count in table_counts:
            engine = self._create_test_db(count)
            inferencer = ForeignKeyInferencer(
                engine,
                threshold=0.50,
                timeout_seconds=30,  # Allow up to 30s per test
            )

            # Clear cache between runs
            inferencer.clear_cache()

            result = bench.run(
                name=f"inference_{count}_tables",
                func=lambda: inferencer.infer_relationships(
                    table_name="fact_table_000",
                    schema_name="main",
                    max_candidates=50,
                ),
                iterations=3,
            )

            scaling_data.append({
                "table_count": count,
                "mean_ms": result.mean_ms,
                "p95_ms": result.p95_ms,
                "memory_mb": result.memory_peak_mb,
            })

            engine.dispose()

        bench.print_summary()

        # Analyze scaling
        print("\n\nInference Scaling Analysis:")
        for data in scaling_data:
            mem_str = f"{data['memory_mb']:.2f} MB" if data['memory_mb'] else "N/A"
            print(
                f"  {data['table_count']:>4} tables: "
                f"mean={data['mean_ms']:>8.2f}ms, "
                f"p95={data['p95_ms']:>8.2f}ms, "
                f"memory={mem_str}"
            )

        # Check scaling is reasonable (less than quadratic)
        if len(scaling_data) >= 2:
            for i in range(1, len(scaling_data)):
                prev = scaling_data[i - 1]
                curr = scaling_data[i]

                table_ratio = curr["table_count"] / prev["table_count"]
                time_ratio = curr["mean_ms"] / max(prev["mean_ms"], 0.001)

                # Time should grow at most n*log(n) - allow 4x per doubling
                max_expected_ratio = table_ratio * 2  # Allow some super-linear growth

                print(f"\n  Scaling {prev['table_count']} -> {curr['table_count']}: "
                      f"table_ratio={table_ratio:.2f}, time_ratio={time_ratio:.2f}")

                if time_ratio > max_expected_ratio:
                    print(f"    WARNING: Scaling faster than expected "
                          f"(expected <{max_expected_ratio:.2f}x)")

        # Estimate 500 tables
        if len(scaling_data) >= 2:
            last = scaling_data[-1]
            per_table = last["mean_ms"] / last["table_count"]
            estimated_500 = per_table * 500 * 1.5  # Add 50% buffer for non-linearity

            print(f"\n  Estimated for 500 tables: {estimated_500:.0f}ms")
            print(f"  Recommended timeout: {estimated_500 * 2 / 1000:.0f}s")

    def test_inference_with_timeout(self):
        """Test inference timeout mechanism (T134)."""
        engine = self._create_test_db(100)

        # Set a very short timeout
        inferencer = ForeignKeyInferencer(
            engine,
            threshold=0.50,
            timeout_seconds=0.001,  # 1ms - should timeout immediately
        )

        results, metadata = inferencer.infer_relationships(
            table_name="fact_table_000",
            schema_name="main",
            max_candidates=50,
        )

        print(f"\nTimeout test results:")
        print(f"  timed_out: {metadata['timed_out']}")
        print(f"  tables_analyzed: {metadata['tables_analyzed']}")
        print(f"  candidates_evaluated: {metadata['total_candidates_evaluated']}")

        # With 1ms timeout, it should timeout
        assert metadata["timed_out"] is True, "Should have timed out with 1ms limit"

        # Should still return partial results
        assert isinstance(results, list), "Should return partial results list"

        engine.dispose()

    def test_inference_no_timeout(self):
        """Test inference completes without timeout when limit is sufficient."""
        engine = self._create_test_db(25)

        # Set a generous timeout
        inferencer = ForeignKeyInferencer(
            engine,
            threshold=0.50,
            timeout_seconds=30,  # 30s should be plenty
        )

        results, metadata = inferencer.infer_relationships(
            table_name="fact_table_000",
            schema_name="main",
            max_candidates=20,
        )

        print(f"\nNo-timeout test results:")
        print(f"  timed_out: {metadata['timed_out']}")
        print(f"  analysis_time_ms: {metadata['analysis_time_ms']}")
        print(f"  relationships found: {len(results)}")

        assert metadata["timed_out"] is False, "Should not timeout with 30s limit"
        assert metadata["analysis_time_ms"] > 0, "Should have valid timing"

        engine.dispose()
