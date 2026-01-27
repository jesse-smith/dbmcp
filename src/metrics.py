"""Performance metrics tracking.

T127/T128: Provides p50, p95, p99 latency tracking for monitoring
service performance against NFR-001 and NFR-002 requirements.

Usage:
    from src.metrics import PerformanceMetrics

    metrics = PerformanceMetrics.get_instance()

    # Record operation timing
    with metrics.track("list_tables"):
        result = service.list_tables()

    # Get statistics
    stats = metrics.get_stats("list_tables")
    print(f"p95 latency: {stats['p95_ms']:.2f}ms")
"""

import statistics
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generator


@dataclass
class OperationStats:
    """Statistics for a tracked operation."""

    operation: str
    samples: list[float] = field(default_factory=list)
    total_calls: int = 0
    errors: int = 0
    last_call: datetime | None = None

    @property
    def min_ms(self) -> float:
        """Minimum latency in milliseconds."""
        return min(self.samples) * 1000 if self.samples else 0

    @property
    def max_ms(self) -> float:
        """Maximum latency in milliseconds."""
        return max(self.samples) * 1000 if self.samples else 0

    @property
    def mean_ms(self) -> float:
        """Mean latency in milliseconds."""
        return statistics.mean(self.samples) * 1000 if self.samples else 0

    @property
    def p50_ms(self) -> float:
        """50th percentile (median) latency in milliseconds."""
        return statistics.median(self.samples) * 1000 if self.samples else 0

    @property
    def p95_ms(self) -> float:
        """95th percentile latency in milliseconds."""
        if not self.samples:
            return 0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)] * 1000

    @property
    def p99_ms(self) -> float:
        """99th percentile latency in milliseconds."""
        if not self.samples:
            return 0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)] * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "operation": self.operation,
            "total_calls": self.total_calls,
            "errors": self.errors,
            "sample_count": len(self.samples),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "last_call": self.last_call.isoformat() if self.last_call else None,
        }


class PerformanceMetrics:
    """Singleton performance metrics tracker.

    Tracks operation latencies and provides percentile statistics (p50, p95, p99)
    for monitoring service performance.

    Thread-safe for concurrent operations.

    Usage:
        metrics = PerformanceMetrics.get_instance()

        # Using context manager
        with metrics.track("operation_name"):
            do_something()

        # Manual timing
        start = time.perf_counter()
        do_something()
        metrics.record("operation_name", time.perf_counter() - start)

        # Get statistics
        print(metrics.get_stats("operation_name"))
    """

    _instance: "PerformanceMetrics | None" = None
    _lock = threading.Lock()

    # Maximum samples to keep per operation (rolling window)
    MAX_SAMPLES = 1000

    def __init__(self):
        """Initialize metrics tracker. Use get_instance() instead."""
        self._stats: dict[str, OperationStats] = defaultdict(
            lambda: OperationStats(operation="")
        )
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "PerformanceMetrics":
        """Get the singleton metrics instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = PerformanceMetrics()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset the singleton instance (mainly for testing)."""
        with cls._lock:
            cls._instance = None

    @contextmanager
    def track(self, operation: str) -> Generator[None, None, None]:
        """Context manager for timing an operation.

        Args:
            operation: Name of the operation to track

        Yields:
            None

        Example:
            with metrics.track("list_tables"):
                tables = service.list_tables()
        """
        start = time.perf_counter()
        error = False
        try:
            yield
        except Exception:
            error = True
            raise
        finally:
            elapsed = time.perf_counter() - start
            self.record(operation, elapsed, error=error)

    def record(self, operation: str, elapsed_seconds: float, error: bool = False):
        """Record a timing observation.

        Args:
            operation: Name of the operation
            elapsed_seconds: Time taken in seconds
            error: Whether the operation resulted in an error
        """
        with self._lock:
            stats = self._stats[operation]
            if not stats.operation:
                stats.operation = operation

            stats.total_calls += 1
            stats.last_call = datetime.now()

            if error:
                stats.errors += 1
            else:
                stats.samples.append(elapsed_seconds)

                # Rolling window - remove oldest if exceeding max
                if len(stats.samples) > self.MAX_SAMPLES:
                    stats.samples = stats.samples[-self.MAX_SAMPLES:]

    def get_stats(self, operation: str) -> dict[str, Any]:
        """Get statistics for an operation.

        Args:
            operation: Name of the operation

        Returns:
            Dictionary with min, max, mean, p50, p95, p99 latencies
        """
        with self._lock:
            if operation in self._stats:
                return self._stats[operation].to_dict()
            return {"operation": operation, "total_calls": 0}

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all tracked operations.

        Returns:
            Dictionary mapping operation names to their statistics
        """
        with self._lock:
            return {op: stats.to_dict() for op, stats in self._stats.items()}

    def get_summary(self) -> str:
        """Get a formatted summary of all tracked operations.

        Returns:
            Formatted string with performance summary
        """
        lines = ["Performance Metrics Summary", "=" * 60]

        with self._lock:
            for op, stats in sorted(self._stats.items()):
                lines.append(f"\n{op}:")
                lines.append(f"  Calls: {stats.total_calls} (errors: {stats.errors})")
                if stats.samples:
                    lines.append(f"  p50:   {stats.p50_ms:8.2f} ms")
                    lines.append(f"  p95:   {stats.p95_ms:8.2f} ms")
                    lines.append(f"  p99:   {stats.p99_ms:8.2f} ms")
                    lines.append(f"  mean:  {stats.mean_ms:8.2f} ms")

        return "\n".join(lines)

    def clear(self, operation: str | None = None):
        """Clear recorded statistics.

        Args:
            operation: Specific operation to clear, or None for all
        """
        with self._lock:
            if operation:
                if operation in self._stats:
                    del self._stats[operation]
            else:
                self._stats.clear()


# Convenience function for module-level access
def get_metrics() -> PerformanceMetrics:
    """Get the global performance metrics instance."""
    return PerformanceMetrics.get_instance()
