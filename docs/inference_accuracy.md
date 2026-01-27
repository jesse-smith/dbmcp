# FK Inference Algorithm Accuracy Baseline

**Document Version**: 1.0
**Date**: 2026-01-26
**Test Suite**: `tests/integration/test_fk_inference.py`

## Overview

This document describes the FK inference algorithm's accuracy characteristics and provides baseline metrics for regression testing and future improvement.

## Algorithm Description

The FK inference algorithm uses a three-factor weighted scoring system:

| Factor | Weight | Description |
|--------|--------|-------------|
| Name Similarity | 40% | Column/table name pattern matching |
| Type Compatibility | 15% | Data type group compatibility (veto power if incompatible) |
| Structural Hints | 45% | PK, nullable, unique index indicators |

### Scoring Formula

```
confidence = (name_similarity * 0.40) + (type_weight * 0.15) + (structural_score * 0.45)
```

Where:
- `name_similarity`: 0.0-1.0 based on column name matching patterns
- `type_weight`: 1.0 if compatible, 0.0 otherwise (also vetoes result if incompatible)
- `structural_score`: 0.0-1.0 based on structural indicators

## Test Methodology

### Ground Truth Database

The test database consists of:
- 5 dimension tables (customers, products, employees, regions, categories)
- 10 fact tables with declared FKs (orders_00 through orders_09)
- 10 fact tables with undeclared but inferable FKs (sales_00 through sales_09)

**Total Tables**: 25
**Expected Relationships**: 60 (30 declared + 30 undeclared)

### Test Configuration

```python
inferencer = ForeignKeyInferencer(engine, threshold=0.50)
max_candidates = 50
```

## Baseline Metrics

### Default Configuration (threshold=0.50)

| Metric | Value | Notes |
|--------|-------|-------|
| Recall | 100% | All valid relationships found |
| Precision | 6% | Many false positives at low threshold |
| F1 Score | 11.32% | Dominated by precision |
| True Positives | 60 | All expected relationships |
| False Positives | 940 | Over-inclusive at default threshold |
| False Negatives | 0 | No missed relationships |

### Threshold Impact Analysis

| Threshold | Relationships Found | Notes |
|-----------|---------------------|-------|
| 0.30 | More | More permissive, higher recall |
| 0.50 | Moderate | Default threshold |
| 0.70 | Fewer | More selective, higher precision |

## Algorithm Characteristics

### Strengths

1. **High Recall**: The algorithm is designed to not miss valid relationships
2. **Pattern Recognition**: Effectively identifies `_id` suffix patterns
3. **Type Safety**: Filters out type-incompatible relationships
4. **Structural Analysis**: Uses PK/nullable/unique constraints as signals

### Limitations

1. **Low Precision at Default Threshold**: The 0.50 threshold produces many false positives
2. **No Value Overlap Analysis**: Phase 1 does not analyze actual data values
3. **Generic Integer Matching**: All integer columns may match each other
4. **Naming Convention Dependent**: Works best with consistent naming patterns

### Recommendations for Higher Precision

1. **Increase Threshold**: Use threshold=0.70+ for fewer false positives
2. **Enable Value Overlap**: Phase 2 feature will analyze actual data overlap
3. **Consistent Naming**: Use distinctive naming conventions (e.g., `customer_id` vs `cust_no`)
4. **Human Review**: Always have humans validate inferred relationships

## Known False Positive Patterns

At threshold=0.50, the algorithm generates false positives when:

1. **Generic ID columns**: `customer_id` matches any table with an `id` column
2. **Similar type columns**: All INTEGER columns are type-compatible
3. **Cross-table matching**: FK columns in one fact table match PKs in other fact tables

## Future Improvements

### Phase 2 Features (Planned)

- Value overlap analysis to improve precision
- Statistical sampling for large tables
- Cardinality ratio analysis
- Join validation via sample queries

### Potential Algorithm Enhancements

- Table name matching (e.g., `customer_id` should prefer `customers` table)
- Naming convention presets (snake_case, camelCase, etc.)
- Custom pattern rules per database
- Machine learning-based confidence scoring

## Test Suite Coverage

The accuracy test suite (`tests/integration/test_fk_inference.py`) includes:

| Test | Description |
|------|-------------|
| `test_inference_accuracy_on_ground_truth` | Full accuracy metrics calculation |
| `test_precision_on_declared_fks` | Validates declared FK detection |
| `test_recall_on_undeclared_fks` | Validates undeclared FK detection |
| `test_confidence_threshold_impact` | Tests threshold parameter behavior |
| `test_max_candidates_limiting` | Tests result limiting |
| `test_name_similarity_scoring` | Unit tests name matching component |
| `test_structural_hints_scoring` | Unit tests structural analysis |
| `test_type_compatibility_filter` | Unit tests type filtering |

## Regression Testing

To run the accuracy baseline tests:

```bash
pytest tests/integration/test_fk_inference.py -v
```

Expected outcome: All 8 tests pass, with documented metrics printed for the ground truth test.

## References

- [FK Inference Implementation](../src/inference/relationships.py)
- [Test Suite](../tests/integration/test_fk_inference.py)
- [Unit Tests](../tests/unit/test_relationships.py)
- [MCP Tool Contract](../specs/001-db-schema-explorer/contracts/mcp_tools.md)
