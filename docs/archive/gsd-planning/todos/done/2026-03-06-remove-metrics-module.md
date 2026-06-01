---
created: 2026-03-06T18:22:28.003Z
title: Remove metrics module
area: general
files:
  - src/metrics.py
  - src/db/metadata.py:NFR_001_THRESHOLD_MS
---

## Problem

`src/metrics.py` (258 lines) implements a `PerformanceMetrics` singleton with p50/p95/p99 latency tracking, but is never imported or used by any other module in the codebase. It's entirely dead code with 0% test coverage. The percentile calculations also have a correctness issue (truncating `int(len() * 0.95)` instead of proper percentile math for small samples).

The NFR-001/NFR-002 performance thresholds defined in `src/db/metadata.py` reference this module conceptually but there's no actual integration.

## Solution

Delete `src/metrics.py` entirely. If performance tracking is needed in the future, reimplement using `statistics.quantiles()` (Python 3.8+) or a proper observability library rather than reviving this dead code. Also clean up the NFR threshold constants in `metadata.py` if they're only referenced by the metrics module.
