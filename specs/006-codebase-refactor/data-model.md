# Data Model: Codebase Refactor

**Feature**: 006-codebase-refactor
**Date**: 2026-02-27

## Overview

This feature does not introduce new data entities. It restructures existing code without changing data models or public interfaces.

## Existing Dataclass Inventory (19 total)

### models/schema.py (10 dataclasses)
- `DenialReason` — Query denial reason (category, detail, statement_index)
- `ValidationResult` — Query validation outcome (is_safe, reasons)
- `Connection` — Database connection metadata
- `Schema` — Database schema entity
- `Table` — Database table entity
- `Column` — Database column entity (16 fields)
- `Index` — Database index entity
- `DocumentationCache` — Cache metadata
- `Query` — SQL query execution record
- `SampleData` — Table sample data container

### models/relationship.py (3 dataclasses)
- `InferenceFactors` — FK inference scoring breakdown
- `Relationship` — Base FK relationship (parent class)
  - `DeclaredFK` — Schema-defined FK (inherits Relationship)
  - `InferredFK` — Algorithm-inferred FK (inherits Relationship)

### metrics.py (1 dataclass)
- `OperationStats` — Performance metrics for single operation

### inference/columns.py (4 dataclasses)
- `NumericStats`, `DateTimeStats`, `StringStats` — Column statistics by type
- `ColumnAnalysis` — Complete column analysis result

### inference/relationships.py (1 dataclass)
- `ColumnInfo` — Lightweight column metadata for FK inference

## Changes During Refactor

### Naming Standardization
- `ColumnInfo.is_pk` → rename to `is_primary_key` for consistency with `Column.is_primary_key`
- Update all references in relationships.py and tests

### Relocation
- `NumericStats`, `DateTimeStats`, `StringStats`, `ColumnAnalysis` remain in inference/columns.py (or its decomposed submodule) — they are tightly coupled to the analysis logic
- `ColumnInfo` remains in inference/relationships.py (or its decomposed submodule) — single use site
- No dataclasses move to models/ — they are implementation details, not shared domain models

### No Consolidation
- `Column` and `ColumnInfo` serve different lifecycles (persistent vs ephemeral) and will not be merged
- Statistics dataclasses are domain-specific and non-overlapping
