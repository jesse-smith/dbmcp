"""Performance benchmarking utility.

T122: Provides timing, memory usage, and statistics tracking for performance tests.

This module implements:
- High-precision timing with statistics (min, max, mean, p50, p95, p99)
- Memory usage tracking
- Benchmark result recording and comparison
- Report generation
"""

import gc
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    iterations: int
    times: list[float] = field(default_factory=list)
    memory_peak_bytes: int | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def min_ms(self) -> float:
        """Minimum execution time in milliseconds."""
        return min(self.times) * 1000 if self.times else 0

    @property
    def max_ms(self) -> float:
        """Maximum execution time in milliseconds."""
        return max(self.times) * 1000 if self.times else 0

    @property
    def mean_ms(self) -> float:
        """Mean execution time in milliseconds."""
        return statistics.mean(self.times) * 1000 if self.times else 0

    @property
    def stdev_ms(self) -> float:
        """Standard deviation of execution time in milliseconds."""
        return statistics.stdev(self.times) * 1000 if len(self.times) > 1 else 0

    @property
    def p50_ms(self) -> float:
        """50th percentile (median) execution time in milliseconds."""
        return statistics.median(self.times) * 1000 if self.times else 0

    @property
    def p95_ms(self) -> float:
        """95th percentile execution time in milliseconds."""
        if not self.times:
            return 0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)] * 1000

    @property
    def p99_ms(self) -> float:
        """99th percentile execution time in milliseconds."""
        if not self.times:
            return 0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)] * 1000

    @property
    def memory_peak_mb(self) -> float | None:
        """Peak memory usage in megabytes."""
        if self.memory_peak_bytes is None:
            return None
        return self.memory_peak_bytes / (1024 * 1024)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "name": self.name,
            "iterations": self.iterations,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "stdev_ms": round(self.stdev_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "memory_peak_mb": round(self.memory_peak_mb, 2) if self.memory_peak_mb else None,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class Benchmark:
    """Performance benchmarking utility.

    Usage:
        bench = Benchmark()

        # Simple timing
        with bench.time("operation_name"):
            do_something()

        # Multiple iterations with statistics
        result = bench.run("list_tables", lambda: service.list_tables(), iterations=10)

        # Generate report
        bench.print_summary()
    """

    def __init__(self, track_memory: bool = True):
        """Initialize benchmark.

        Args:
            track_memory: Whether to track memory usage (adds overhead).
        """
        self.track_memory = track_memory
        self.results: list[BenchmarkResult] = []

    def run(
        self,
        name: str,
        func: Callable,
        iterations: int = 5,
        warmup: int = 1,
        cleanup: Callable | None = None,
    ) -> BenchmarkResult:
        """Run a benchmark function multiple times and collect statistics.

        Args:
            name: Name of the benchmark
            func: Function to benchmark (no arguments)
            iterations: Number of timed iterations
            warmup: Number of warmup iterations (not timed)
            cleanup: Optional cleanup function to call after each iteration

        Returns:
            BenchmarkResult with timing statistics
        """
        result = BenchmarkResult(name=name, iterations=iterations)

        # Warmup runs (not timed)
        for _ in range(warmup):
            try:
                func()
                if cleanup:
                    cleanup()
            except Exception as e:
                result.error = f"Warmup failed: {str(e)}"
                self.results.append(result)
                return result

        # Garbage collect before timing
        gc.collect()

        # Track memory if enabled
        if self.track_memory:
            tracemalloc.start()

        try:
            # Timed runs
            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    func()
                except Exception as e:
                    result.error = f"Iteration failed: {str(e)}"
                    break
                end = time.perf_counter()
                result.times.append(end - start)

                if cleanup:
                    cleanup()

            # Get memory peak
            if self.track_memory:
                _, peak = tracemalloc.get_traced_memory()
                result.memory_peak_bytes = peak

        finally:
            if self.track_memory:
                tracemalloc.stop()

        self.results.append(result)
        return result

    class _TimerContext:
        """Context manager for timing code blocks."""

        def __init__(self, benchmark: "Benchmark", name: str):
            self.benchmark = benchmark
            self.name = name
            self.start_time: float = 0
            self.result: BenchmarkResult | None = None

        def __enter__(self):
            if self.benchmark.track_memory:
                tracemalloc.start()
            gc.collect()
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = time.perf_counter() - self.start_time

            memory_peak = None
            if self.benchmark.track_memory:
                _, peak = tracemalloc.get_traced_memory()
                memory_peak = peak
                tracemalloc.stop()

            error = None
            if exc_type:
                error = f"{exc_type.__name__}: {exc_val}"

            self.result = BenchmarkResult(
                name=self.name,
                iterations=1,
                times=[elapsed],
                memory_peak_bytes=memory_peak,
                error=error,
            )
            self.benchmark.results.append(self.result)

            return False  # Don't suppress exceptions

    def time(self, name: str) -> _TimerContext:
        """Context manager for timing a code block.

        Usage:
            with bench.time("my_operation"):
                do_something()
        """
        return self._TimerContext(self, name)

    def print_summary(self):
        """Print a summary of all benchmark results."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 80)

        for result in self.results:
            status = "PASS" if result.error is None else "FAIL"
            print(f"\n{result.name} [{status}]")
            print("-" * 40)

            if result.error:
                print(f"  Error: {result.error}")
            else:
                print(f"  Iterations: {result.iterations}")
                print(f"  Min:   {result.min_ms:10.2f} ms")
                print(f"  Max:   {result.max_ms:10.2f} ms")
                print(f"  Mean:  {result.mean_ms:10.2f} ms")
                print(f"  StDev: {result.stdev_ms:10.2f} ms")
                print(f"  p50:   {result.p50_ms:10.2f} ms")
                print(f"  p95:   {result.p95_ms:10.2f} ms")
                print(f"  p99:   {result.p99_ms:10.2f} ms")

                if result.memory_peak_mb:
                    print(f"  Memory Peak: {result.memory_peak_mb:.2f} MB")

        print("\n" + "=" * 80)

    def get_report(self) -> dict[str, Any]:
        """Get benchmark results as a dictionary for reporting."""
        return {
            "timestamp": datetime.now().isoformat(),
            "python_version": sys.version,
            "results": [r.to_dict() for r in self.results],
        }

    def clear(self):
        """Clear all recorded results."""
        self.results.clear()


def benchmark_function(
    func: Callable,
    name: str | None = None,
    iterations: int = 5,
    track_memory: bool = True,
) -> BenchmarkResult:
    """Convenience function to benchmark a single function.

    Args:
        func: Function to benchmark
        name: Name for the benchmark (defaults to function name)
        iterations: Number of iterations
        track_memory: Whether to track memory

    Returns:
        BenchmarkResult with statistics
    """
    bench = Benchmark(track_memory=track_memory)
    result = bench.run(
        name=name or func.__name__,
        func=func,
        iterations=iterations,
    )
    return result


def assert_performance(
    func: Callable,
    max_ms: float,
    name: str | None = None,
    iterations: int = 3,
) -> BenchmarkResult:
    """Assert that a function completes within a time limit.

    Args:
        func: Function to benchmark
        max_ms: Maximum allowed execution time in milliseconds
        name: Name for the benchmark
        iterations: Number of iterations to run

    Returns:
        BenchmarkResult

    Raises:
        AssertionError: If p95 time exceeds max_ms
    """
    result = benchmark_function(func, name=name, iterations=iterations)

    assert result.error is None, f"Benchmark failed with error: {result.error}"
    assert result.p95_ms <= max_ms, (
        f"Performance assertion failed for {result.name}: "
        f"p95={result.p95_ms:.2f}ms > max={max_ms}ms"
    )

    return result
