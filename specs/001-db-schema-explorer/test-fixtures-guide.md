# Test Fixtures Guide: Database Schema Explorer

**Purpose**: Define test database fixtures for validating MCP server functionality and accuracy

**Related Tasks**: T011B (basic test DB), T111 (FK inference ground truth), T121 (performance test DB)

---

## Fixture 1: Basic Test Database (`test_db_schema.sql`)

**Purpose**: General integration testing for all user stories

**Location**: `tests/fixtures/test_db_schema.sql`

### Schema Overview

- **3 schemas**: `sales`, `inventory`, `hr`
- **15 tables** total (5 per schema)
- **20 declared foreign keys**
- **Mix of data types**: int, bigint, varchar, nvarchar, date, datetime, decimal, bit
- **Row counts**: 0 to 10,000 rows per table
- **Special cases**:
  - Empty tables (0 rows)
  - Tables with binary/blob columns
  - Tables with large text columns (>1000 chars)
  - Views (2 views for testing EC-006)

### Example Tables

**sales.Customers** (1000 rows)
- CustomerID (int, PK)
- CustomerName (varchar(100))
- Email (varchar(255))
- CreatedDate (datetime)
- StatusCode (char(1)) - enum test case

**sales.Orders** (5000 rows)
- OrderID (int, PK)
- CustomerID (int, FK → sales.Customers)
- OrderDate (datetime)
- TotalAmount (decimal(10,2))
- ShippingAddress (nvarchar(500))

**inventory.Products** (500 rows)
- ProductID (int, PK)
- ProductName (varchar(200))
- Description (nvarchar(max)) - large text test case
- ProductImage (varbinary(max)) - binary test case
- Price (decimal(10,2))

### Usage

```bash
# Create test database
sqlcmd -S localhost -i tests/fixtures/test_db_schema.sql

# Run integration tests
pytest tests/integration/ -v
```

---

## Fixture 2: FK Inference Ground Truth (`fk_ground_truth.sql`)

**Purpose**: Validate relationship inference accuracy against known correct relationships (SC-003)

**Location**: `tests/fixtures/fk_ground_truth.sql`

### Schema Overview

- **50 tables** across 3 schemas (sales, inventory, hr)
- **80 known valid relationships** (manually verified)
  - **40 declared as foreign keys** (baseline for comparison)
  - **40 valid joins NOT declared as FKs** (inference target)
- **Covers all test scenarios**:
  - Perfect naming match
  - Common variations
  - Abbreviations
  - Type compatibility
  - Structural hints
  - Negative cases (name collisions)

### Test Scenarios Covered

#### 1. Perfect Naming Match (Expected Score: 90%+)
- `sales.Orders.CustomerID` → `sales.Customers.CustomerID`
- Both int, exact name match, CustomerID is PK

#### 2. Common Variations (Expected Score: 80%+)
- `inventory.OrderItems.Order_ID` → `sales.Orders.OrderID`
- Underscore variation, both int

#### 3. Abbreviations (Expected Score: 60-70%)
- `sales.Invoices.CustID` → `sales.Customers.CustomerID`
- Abbreviated name, both int

#### 4. Type Compatibility
- `hr.Employees.ManagerID` (bigint) → `hr.Employees.EmployeeID` (int)
- Should allow: bigint can reference int

#### 5. Structural Hints
- `sales.Orders.CustomerID` (NOT NULL, has index) → `sales.Customers.CustomerID`
- Structural hints boost confidence

#### 6. Negative Cases (Should NOT Match)
- `sales.Orders.ProductID` vs `inventory.Shipments.ProductID`
- Both reference `inventory.Products.ProductID`, but different domains
- Name collision, should not infer cross-relationship

### Ground Truth Metadata

**File**: `tests/fixtures/fk_ground_truth_expected.json`

```json
{
  "declared_fks": [
    {
      "source_table": "sales.Orders",
      "source_column": "CustomerID",
      "target_table": "sales.Customers",
      "target_column": "CustomerID",
      "declared": true
    }
  ],
  "undeclared_valid_joins": [
    {
      "source_table": "inventory.OrderItems",
      "source_column": "Order_ID",
      "target_table": "sales.Orders",
      "target_column": "OrderID",
      "declared": false,
      "expected_confidence": 0.85,
      "rationale": "Name variation (underscore), type compatible"
    }
  ],
  "known_false_positives": [
    {
      "source_table": "sales.Orders",
      "source_column": "ProductID",
      "target_table": "inventory.Shipments",
      "target_column": "ProductID",
      "rationale": "Name collision, different domains"
    }
  ]
}
```

### Accuracy Calculation

**Precision**: (true positives) / (true positives + false positives)
- True Positive: Inferred relationship matches undeclared_valid_joins
- False Positive: Inferred relationship NOT in declared_fks or undeclared_valid_joins

**Recall**: (true positives) / (true positives + false negatives)
- True Positive: Same as above
- False Negative: Relationship in undeclared_valid_joins but NOT inferred

**F1 Score**: 2 * (precision * recall) / (precision + recall)

**Target**: F1 >= 0.80 (per SC-003)

### Usage

```bash
# Create ground truth database
sqlcmd -S localhost -i tests/fixtures/fk_ground_truth.sql

# Run accuracy test
pytest tests/integration/test_fk_inference.py::test_inference_accuracy_meets_sc003 -v

# View detailed accuracy report
cat tests/integration/fk_inference_accuracy_report.md
```

### Maintenance

Update this database when:
- New inference heuristics are added
- Algorithm weights change
- Need to validate regression after refactoring

---

## Fixture 3: Performance Test Database (`perf_test_db.sql`)

**Purpose**: Validate performance requirements (NFR-001, NFR-002, NFR-003)

**Location**: `tests/fixtures/perf_test_db.sql`

### Schema Overview

- **1000 tables** (simulates large enterprise database)
- **Table sizes**: 0 to 100,000 rows per table
  - 100 empty tables (0 rows)
  - 400 small tables (1-100 rows)
  - 300 medium tables (101-10,000 rows)
  - 150 large tables (10,001-50,000 rows)
  - 50 very large tables (50,001-100,000 rows)
- **10 schemas** (schema_0 through schema_9)
- **Simple structure**: Each table has 5-10 columns for fast generation

### Table Naming Pattern

- `schema_0.table_000` through `schema_9.table_999`
- Deterministic generation for reproducibility

### Performance Targets

| NFR | Test | Target | Test Task |
|-----|------|--------|-----------|
| NFR-001 | Metadata queries | <30s for 1000 tables | T123 |
| NFR-002 | Sample data | <10s per table | T124 |
| NFR-003 | Documentation size | <1MB for 500 tables | T125 |
| - | FK inference scaling | Measure complexity | T126 |

### Generation Script

The SQL script uses a loop to generate tables programmatically:

```sql
DECLARE @schema_num INT = 0;
DECLARE @table_num INT = 0;
DECLARE @table_name NVARCHAR(100);
DECLARE @sql NVARCHAR(MAX);

WHILE @schema_num < 10
BEGIN
    SET @table_num = 0;
    WHILE @table_num < 100
    BEGIN
        SET @table_name = 'schema_' + CAST(@schema_num AS VARCHAR) + '.table_'
                          + RIGHT('000' + CAST(@table_num AS VARCHAR), 3);

        SET @sql = 'CREATE TABLE ' + @table_name + ' (
            ID INT PRIMARY KEY IDENTITY(1,1),
            Column1 VARCHAR(100),
            Column2 INT,
            Column3 DATETIME,
            Column4 DECIMAL(10,2),
            Column5 NVARCHAR(255)
        )';

        EXEC sp_executesql @sql;

        -- Insert rows based on table number (varied distribution)
        -- (row insertion logic here)

        SET @table_num = @table_num + 1;
    END
    SET @schema_num = @schema_num + 1;
END
```

### Usage

```bash
# Create performance test database (WARNING: Takes ~10 minutes)
sqlcmd -S localhost -i tests/fixtures/perf_test_db.sql

# Run performance validation suite
pytest tests/performance/ -v --benchmark

# Generate performance report
python tests/performance/report.py --output baseline.md
```

### Baseline Report Format

**File**: `tests/performance/baseline.md`

```markdown
# Performance Baseline Report

**Date**: 2026-01-19
**Database**: perf_test (1000 tables)
**Test Environment**: [System specs]

## NFR-001: Metadata Query Performance

| Operation | Tables | Duration | Status |
|-----------|--------|----------|--------|
| list_schemas | 10 | 0.8s | ✅ PASS |
| list_tables | 1000 | 24.3s | ✅ PASS (<30s) |
| get_table_schema | 1 | 0.3s | ✅ PASS |

## NFR-002: Sample Data Performance

| Table Size | Sample Size | Duration | Status |
|------------|-------------|----------|--------|
| 100 rows | 5 | 0.2s | ✅ PASS |
| 10K rows | 5 | 0.8s | ✅ PASS |
| 100K rows | 5 | 2.1s | ✅ PASS |

## NFR-003: Documentation Size

| Tables | Doc Size | Status |
|--------|----------|--------|
| 500 | 742 KB | ✅ PASS (<1MB) |

## FK Inference Scaling

| Tables | Duration | Candidates | Complexity |
|--------|----------|------------|------------|
| 50 | 1.2s | 15 | O(n²) |
| 100 | 4.8s | 58 | O(n²) |
| 250 | 29.1s | 342 | O(n²) |
```

---

## Fixture Management

### Directory Structure

```
tests/fixtures/
├── test_db_schema.sql           # Basic integration test DB
├── fk_ground_truth.sql          # Accuracy validation DB
├── fk_ground_truth_expected.json # Ground truth metadata
├── perf_test_db.sql             # Performance test DB
└── README.md                    # This file (copy)
```

### Maintenance Checklist

- [ ] Update fixtures when new features added
- [ ] Regenerate ground truth when inference algorithm changes
- [ ] Validate fixture SQL scripts run cleanly on fresh SQL Server instance
- [ ] Document any SQL Server version requirements
- [ ] Keep expected results JSON in sync with SQL fixtures

### Docker Setup (Optional)

For consistent testing environment:

```bash
# Start SQL Server container
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=TestP@ssw0rd" \
  -p 1433:1433 -d mcr.microsoft.com/mssql/server:2022-latest

# Load fixtures
sqlcmd -S localhost -U sa -P "TestP@ssw0rd" -i tests/fixtures/test_db_schema.sql
```

---

## Related Documentation

- Constitution Principle III: Test-First Development (`.specify/memory/constitution.md:59`)
- Success Criteria SC-003: FK inference accuracy (spec.md:272)
- Performance Requirements: NFR-001, NFR-002, NFR-003 (spec.md:250-252)
- Integration test tasks: T110, T111, T112 (tasks.md:274-290)
- Performance validation tasks: T123-T126 (tasks.md:300-303)
