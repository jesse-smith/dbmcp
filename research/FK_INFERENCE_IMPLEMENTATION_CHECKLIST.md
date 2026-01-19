# Foreign Key Inference - Implementation Checklist

## Phase 1: Metadata-Only Inference (2-4 hours)

### 1. Data Models
- [ ] Create `src/models/relationship.py`
  - [ ] `InferredFK` dataclass with fields: source_table, source_column, target_table, target_column, confidence, reason
  - [ ] `MatchContext` dataclass for scoring details (for debugging)

### 2. Core Algorithm Implementation
- [ ] Create `src/inference/relationships.py`
  - [ ] `ForeignKeyInferencer` class
  - [ ] `__init__` with configurable confidence_threshold
  - [ ] `infer_relationships(tables_metadata) -> List[InferredFK]`
  - [ ] Private methods:
    - [ ] `_score_match()` - Main scoring logic
    - [ ] `_score_name_match()` - 40% weight
    - [ ] `_score_type_match()` - 15% weight (with veto for incompatible types)
    - [ ] `_score_structural()` - 45% weight
    - [ ] `_explain_match()` - Human-readable reasoning

### 3. Integration with Database Inspection
- [ ] In `src/db/metadata.py` (or similar):
  - [ ] Extract column metadata into format: `{name, type, is_pk, is_nullable, is_unique}`
  - [ ] Call `ForeignKeyInferencer.infer_relationships()` with metadata
  - [ ] Sort results by confidence (highest first)
  - [ ] Filter by confidence threshold (default 50%)

### 4. MCP Tool Exposure
- [ ] In `src/mcp_server/tools.py`:
  - [ ] Add tool: `infer_relationships`
  - [ ] Input parameters:
    - [ ] `tables` (required): List of table names to analyze (or [] for all)
    - [ ] `confidence_threshold` (optional): Override default (0-1 scale)
    - [ ] `include_details` (optional): Return match reasoning
  - [ ] Output format:
    ```json
    {
      "inferred_relationships": [
        {
          "source": "Orders.CustomerID",
          "target": "Customers.ID",
          "confidence": 0.96,
          "reason": "Name similarity + type match + structural hints"
        }
      ],
      "stats": {
        "total_relationships": 3,
        "high_confidence": 2,  // >= 0.80
        "medium_confidence": 1,  // 0.50-0.80
        "analysis_time_ms": 145
      }
    }
    ```

### 5. Unit Tests
- [ ] Create `tests/unit/test_relationships.py`
  - [ ] `test_name_similarity_exact_match()`
  - [ ] `test_name_similarity_high_similarity()`
  - [ ] `test_name_similarity_with_underscores()`
  - [ ] `test_type_compatibility_exact_match()`
  - [ ] `test_type_compatibility_compatible_types()`
  - [ ] `test_type_compatibility_incompatible_veto()`
  - [ ] `test_structural_scoring_pk_target()`
  - [ ] `test_structural_scoring_nullable_source()`
  - [ ] `test_end_to_end_scoring()`

### 6. Integration Tests
- [ ] Create `tests/integration/test_fk_inference.py`
  - [ ] Set up test database with:
    - [ ] `Orders` (OrderID PK, CustomerID FK)
    - [ ] `Customers` (ID PK)
    - [ ] `OrderItems` (ItemID PK, Order_ID FK, ProductID FK)
    - [ ] `Products` (ProductID PK, CategoryID undeclared FK)
  - [ ] Run inference on test database
  - [ ] Assert correctly identifies:
    - [ ] Orders.CustomerID → Customers.ID (declared or inferred)
    - [ ] OrderItems.Order_ID → Orders.OrderID
    - [ ] OrderItems.ProductID → Products.ProductID
    - [ ] Products.CategoryID → ? (category table or null)
  - [ ] Measure accuracy: TP, FP, FN
  - [ ] Verify confidence scores are in 0-1 range
  - [ ] Verify performance: <100ms for small database

### 7. Configuration & Tuning
- [ ] Create `config/inference.yaml` (or similar)
  ```yaml
  inference:
    name_weight: 0.40
    type_weight: 0.15
    structural_weight: 0.45
    confidence_threshold: 0.50
    
    # Name matching tuning
    id_suffixes: [_id, _key, _code, _num, _number]
    min_name_similarity: 0.60
    
    # Type matching tuning
    type_groups:
      numeric: [int, bigint, smallint, tinyint, numeric, decimal]
      string: [varchar, nvarchar, char, nchar, text]
      guid: [uniqueidentifier]
      date: [datetime, datetime2, date, time]
  ```
- [ ] Load config on startup
- [ ] Allow override via MCP tool parameters

### 8. Documentation
- [ ] Add docstrings to all public methods
- [ ] Document scoring model in README
- [ ] Add example output to MCP tool documentation
- [ ] Note limitations (no data access, false positives possible)

### 9. Performance Validation
- [ ] Benchmark on small database (10 tables):
  - [ ] Assert inference completes in <100ms
  - [ ] Log time breakdown: metadata retrieval, scoring, sorting
- [ ] Benchmark on medium database (50-100 tables):
  - [ ] Assert inference completes in <1s
- [ ] Profile memory usage (should be minimal - only metadata)

### 10. Quality Gates Before Merge
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Code coverage >80% for inference module
- [ ] No linting errors (black, pylint, mypy)
- [ ] Docstrings for all public methods
- [ ] Performance benchmarks recorded
- [ ] Example output documented

---

## Phase 2: Value Overlap Analysis (Conditional, 1-2 days)

**Only implement if Phase 1 accuracy <70% on real-world databases**

### Trigger Criteria
- [ ] Measure Phase 1 accuracy on production databases
- [ ] If precision <0.70 OR recall <0.70, proceed with Phase 2
- [ ] OR if users explicitly request "detailed" analysis

### Implementation
- [ ] Create `src/inference/value_overlap.py`
  - [ ] `calculate_overlap_ratio()` - Jaccard similarity
  - [ ] `sample_column_values()` - Efficient sampling for large tables
  - [ ] `estimate_overlap_from_sample()` - Statistical estimate
- [ ] Integrate with Phase 1 scoring:
  - [ ] Run Phase 1 first (fast filter)
  - [ ] For top N candidates, run overlap analysis
  - [ ] Adjust confidence based on overlap_ratio
- [ ] Add performance optimizations:
  - [ ] Parallelize sampling across columns
  - [ ] Cache results per session
  - [ ] Implement timeout for long-running analysis

### Testing
- [ ] Integration tests with real data
- [ ] Verify value overlap correctly identifies true FKs
- [ ] Measure accuracy improvement vs Phase 1
- [ ] Verify performance acceptable (1-5s per table pair)

---

## Phase 3: Domain Customization (Only if Needed)

**Only implement if Phase 1/2 accuracy still insufficient or specific domain patterns emerge**

### Implementation
- [ ] Create configuration:
  - [ ] `config/domain_dictionary.yaml` - Synonym mappings
  - [ ] `config/phonetic_rules.yaml` - Abbreviation patterns
- [ ] Implement semantic scoring:
  - [ ] Lookup synonyms (customer = client = buyer)
  - [ ] Apply phonetic matching for abbreviations
  - [ ] Optional: lightweight word embeddings
- [ ] Testing:
  - [ ] Test with domain-specific databases
  - [ ] Validate accuracy improvement

---

## Success Criteria Checklist

### Functional
- [ ] Infers FKs from metadata (no data access)
- [ ] Provides confidence scores (0-1 scale)
- [ ] Explains reasoning for each match
- [ ] Configurable threshold (default 50%)
- [ ] Filters results by confidence
- [ ] Handles databases with 500+ tables efficiently

### Performance
- [ ] <100ms per table for metadata-only analysis
- [ ] No memory bloat (only metadata in memory)
- [ ] Linear scaling with number of tables

### Quality
- [ ] >80% code coverage
- [ ] Accuracy 75-80% on test database (Phase 1)
- [ ] All tests passing
- [ ] No linting errors
- [ ] Clear documentation

### User Experience
- [ ] Results clearly distinguish HIGH/MEDIUM/LOW confidence
- [ ] Reasons explain why relationships were suggested
- [ ] Easy to understand and tune
- [ ] Analyst can override/filter results

---

## Quick Start Command

After completing Phase 1:

```bash
# Run all tests
pytest tests/

# Run coverage
pytest --cov=src/inference tests/unit/test_relationships.py

# Run benchmarks
python -m pytest tests/integration/test_fk_inference.py -v --durations=10

# Try it out
python -c "
from src.inference.relationships import ForeignKeyInferencer
from src.db.metadata import get_table_metadata

inferencer = ForeignKeyInferencer(confidence_threshold=0.5)
metadata = get_table_metadata()
results = inferencer.infer_relationships(metadata)
for r in results:
    print(f'{r.source_table}.{r.source_column} → {r.target_table}.{r.target_column} ({r.confidence:.0%})')
"
```

---

## Files to Create/Modify

### New Files
- [ ] `src/models/relationship.py`
- [ ] `src/inference/relationships.py`
- [ ] `tests/unit/test_relationships.py`
- [ ] `tests/integration/test_fk_inference.py`
- [ ] `config/inference.yaml`
- [ ] `docs/inference_algorithm.md` (documentation)

### Modified Files
- [ ] `src/db/metadata.py` - Add integration
- [ ] `src/mcp_server/tools.py` - Add MCP tool
- [ ] `src/mcp_server/server.py` - Register tool
- [ ] `tests/fixtures/` - Add test database schema

---

## Estimated Timeline

| Task | Hours | Notes |
|------|-------|-------|
| 1-2. Data models + algorithm | 1-2 | Core implementation |
| 3-4. DB integration + MCP tool | 0.5-1 | Glue code |
| 5-6. Unit + integration tests | 0.5-1 | Comprehensive test coverage |
| 7-8. Configuration + docs | 0.5-1 | Config and documentation |
| 9. Performance validation | 0.5 | Benchmarking |
| 10. Quality gates + cleanup | 0.5 | Final polish |
| **TOTAL** | **3.5-6 hours** | **Likely 4-5 hours in practice** |

---

## Rollout Plan

### MVP (Day 1)
- [ ] Implement Phase 1 algorithm
- [ ] Basic unit tests
- [ ] Simple integration test with small database
- [ ] MCP tool exposure (basic)

### Beta (Day 2)
- [ ] Extended integration tests
- [ ] Configuration system
- [ ] Performance benchmarks
- [ ] Improved MCP tool responses

### Production (Day 3)
- [ ] Quality gates passed
- [ ] Documentation complete
- [ ] Real-world testing on multiple databases
- [ ] Tuning based on feedback

---

## Known Limitations & Future Work

### Current Limitations (Phase 1)
- No data access (can miss FKs without naming patterns)
- False positives if multiple columns have similar types
- Doesn't handle domain-specific synonyms
- Doesn't handle abbreviations well

### Future Enhancements (Phase 2+)
- Value overlap analysis (reduces false positives)
- Domain dictionary (handles synonyms)
- Phonetic matching (handles abbreviations)
- Semantic analysis with embeddings (handles creative naming)
- ML model trained on domain-specific data

### Won't Do (YAGNI)
- Support for NoSQL databases (out of scope)
- Real-time streaming inference (batch processing assumed)
- Multi-model support (SQL Server only for v1)

