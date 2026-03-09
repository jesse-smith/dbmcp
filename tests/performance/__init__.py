"""Performance testing suite for Database Schema Explorer.

This package provides comprehensive performance validation including:

T121: Performance test fixture (1000-table SQL script)
T122: Benchmark utility (timing, memory tracking)
T123: NFR-001 validation (<30s metadata retrieval)
T124: NFR-002 validation (<10s sample data)
T125: NFR-003 validation (<1MB documentation)
T126: FK inference scaling profile
T127-T128: Performance metrics (module removed — metrics.py was dead code)
T129: Report generator
T130: Baseline report generation

Run the performance suite:
    pytest tests/performance/ -v --benchmark

Note: Full performance tests require a properly-sized test database.
For quick validation, use tests/compliance/ instead.
"""
