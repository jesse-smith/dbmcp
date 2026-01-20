# Data Model: Example Notebooks

**Feature**: 002-example-notebooks
**Date**: 2026-01-20
**Purpose**: Define data structures and schemas for example notebooks feature

## Overview

This feature involves two types of data: notebook metadata and test database schema. The notebooks themselves are `.ipynb` JSON files with a standardized structure. The test database provides sample data for examples.

## Entities

### 1. Notebook Metadata (within .ipynb structure)

**Description**: Metadata embedded in Jupyter notebook files to track version compatibility and maintenance.

**Attributes**:
- `notebook_version`: Semantic version of notebook content (e.g., "1.0.0")
- `dbmcp_version_min`: Minimum compatible DBMCP version (e.g., "0.1.0")
- `dbmcp_version_max`: Maximum tested DBMCP version (e.g., "0.2.0") [optional]
- `last_updated`: ISO 8601 date of last content update (e.g., "2026-01-20")
- `test_database_version`: Version of test database schema required (e.g., "1.0")

**Implementation**: Stored in first markdown cell of each notebook:
```markdown
**Notebook Version**: 1.0.0
**Compatible with DBMCP**: 0.1.0+
**Last Updated**: 2026-01-20
**Test Database Version**: 1.0
```

**Validation Rules**:
- Version numbers must follow semver format (major.minor.patch)
- Last updated must be ISO 8601 date
- Updates to notebook content must increment version and update date

---

### 2. Example Index Entry

**Description**: Structured information about each notebook in the README index.

**Attributes**:
- `filename`: Notebook filename (e.g., "01_basic_connection.ipynb")
- `title`: Human-readable title (e.g., "Basic Connection and Schema Discovery")
- `difficulty`: One of ["Beginner", "Intermediate", "Advanced"]
- `estimated_time`: Minutes to complete (e.g., 5, 10, 15)
- `prerequisites`: List of concepts/notebooks required (e.g., ["Python basics", "SQL familiarity"])
- `features_demonstrated`: List of DBMCP operations (e.g., ["connect_database", "list_schemas"])
- `learning_objectives`: List of what users will learn (e.g., ["Connect to a database", "List schemas"])

**Relationships**:
- Maps to specific `.ipynb` file via `filename`
- References test database via implied dependency

**Implementation**: Markdown table in examples/README.md

---

### 3. Test Database Schema

**Description**: Sample database structure for running examples. Represents typical e-commerce domain.

**Tables**:

#### customers
- `customer_id` (INT, PRIMARY KEY, IDENTITY)
- `email` (VARCHAR(255), UNIQUE, NOT NULL)
- `first_name` (VARCHAR(100), NOT NULL)
- `last_name` (VARCHAR(100), NOT NULL)
- `created_at` (DATETIME, DEFAULT GETDATE())

**Purpose**: Demonstrate basic table with identity PK and unique constraint

#### products
- `product_id` (INT, PRIMARY KEY, IDENTITY)
- `name` (VARCHAR(200), NOT NULL)
- `category` (VARCHAR(50))
- `price` (DECIMAL(10,2), NOT NULL)
- `stock_quantity` (INT, DEFAULT 0)

**Purpose**: Demonstrate decimal types and default values

#### orders
- `order_id` (INT, PRIMARY KEY, IDENTITY)
- `customer_id` (INT, FOREIGN KEY → customers.customer_id)
- `order_date` (DATETIME, DEFAULT GETDATE())
- `status` (VARCHAR(20), CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')))
- `total_amount` (DECIMAL(10,2))

**Purpose**: Demonstrate declared foreign key and CHECK constraint

#### order_items
- `order_item_id` (INT, PRIMARY KEY, IDENTITY)
- `order_id` (INT, FOREIGN KEY → orders.order_id)
- `product_id` (INT, FOREIGN KEY → products.product_id)
- `quantity` (INT, NOT NULL)
- `unit_price` (DECIMAL(10,2), NOT NULL)

**Purpose**: Demonstrate junction table with multiple FKs

#### shipping_addresses
- `address_id` (INT, PRIMARY KEY, IDENTITY)
- `customer_id` (INT, NOT NULL) -- Undeclared FK for inference testing
- `street` (VARCHAR(255))
- `city` (VARCHAR(100))
- `postal_code` (VARCHAR(20))
- `country` (VARCHAR(2), DEFAULT 'US')

**Purpose**: Demonstrate undeclared FK (for relationship inference examples)

#### product_reviews
- `review_id` (INT, PRIMARY KEY, IDENTITY)
- `product_id` (INT, NOT NULL) -- Undeclared FK for inference testing
- `customer_id` (INT, NOT NULL) -- Undeclared FK for inference testing
- `rating` (INT, CHECK (rating BETWEEN 1 AND 5))
- `review_text` (TEXT)
- `created_at` (DATETIME, DEFAULT GETDATE())

**Purpose**: Demonstrate multiple undeclared FKs and rating constraint

**Relationships**:
- Declared: orders → customers, order_items → orders, order_items → products
- Undeclared (for inference): shipping_addresses → customers, product_reviews → products, product_reviews → customers

**Sample Data Volume**:
- customers: 10 rows
- products: 20 rows (4-5 per category)
- orders: 15 rows
- order_items: 30 rows
- shipping_addresses: 12 rows
- product_reviews: 25 rows

**Validation Rules**:
- All foreign keys (declared and undeclared) must reference existing records
- No orphaned records
- Order total_amount should match sum of order_items.unit_price * quantity
- Ratings must be 1-5
- Status must be one of valid enum values

---

### 4. Notebook Helper Utilities

**Description**: Shared Python utilities to reduce boilerplate in notebooks.

**Module**: `examples/shared/notebook_helpers.py`

**Functions**:

#### `setup_connection(connection_string=None) -> Connection`
- **Purpose**: Standard connection setup with error handling
- **Parameters**: Optional connection string (uses env var or default)
- **Returns**: Connected DBMCP connection object
- **Raises**: ConnectionError with helpful message

#### `print_table(data, headers) -> None`
- **Purpose**: Format query results as pretty ASCII table
- **Parameters**: List of rows, column headers
- **Returns**: None (prints to stdout)

#### `verify_notebook_environment() -> bool`
- **Purpose**: Check that all dependencies available
- **Returns**: True if environment valid, False with warning otherwise

**Validation Rules**:
- Helper functions must handle all errors and return user-friendly messages
- No helper function should exceed 20 lines (simplicity principle)
- All helpers must have docstrings

---

## State Transitions

### Notebook Lifecycle

```
Created (v1.0.0)
  ↓
Validated (CI passes)
  ↓
Published (committed to main)
  ↓
[Feature changes]
  ↓
Outdated (failing CI or version mismatch)
  ↓
Updated (version incremented)
  ↓
Validated (CI passes)
  ↓
Published (committed)
```

**Triggers**:
- Created → Validated: CI pipeline executes notebook
- Validated → Published: PR merge
- Published → Outdated: DBMCP API change breaks examples
- Outdated → Updated: Developer updates notebook content
- Updated → Validated: CI pipeline re-executes

---

## Data Volume and Scale

**Storage Requirements**:
- Each notebook: ~50-200 KB (with outputs)
- Test database: ~500 KB (SQLite file)
- Total examples/ directory: ~1-2 MB

**Execution Metrics**:
- Basic notebook: 10-15 cells, ~2-3 minutes execution
- Intermediate notebook: 15-20 cells, ~5-7 minutes execution
- Advanced notebook: 20-25 cells, ~8-10 minutes execution

**Maintenance Frequency**:
- Review on every MCP API change
- Re-execute and validate monthly
- Major updates on DBMCP version releases

---

## Summary

This feature introduces no complex data models—primarily file-based content with simple metadata. The test database uses standard relational patterns familiar to SQL developers. The notebook helper utilities provide minimal abstractions to reduce repetitive code without creating coupling.

**Key Design Decisions**:
1. Metadata embedded in markdown cells (not complex JSON)
2. Test database uses familiar e-commerce domain
3. Mix of declared and undeclared FKs enables full feature demonstration
4. Helper functions kept under 20 lines each (simplicity principle)
5. No state persistence beyond file system (notebooks and database files)
