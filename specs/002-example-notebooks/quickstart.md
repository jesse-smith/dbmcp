# Quick Start: Example Notebooks Implementation

**Feature**: 002-example-notebooks
**Date**: 2026-01-20
**For**: Developers implementing this feature

## 30-Second Overview

Add interactive Jupyter notebook examples to `examples/` directory demonstrating DBMCP functionality. Three notebooks (basic, intermediate, advanced) with shared test database and helper utilities.

## Prerequisites

- DBMCP repository cloned and main project working
- Python 3.11+ environment active
- Jupyter installed: `pip install jupyter notebook`
- Familiarity with Jupyter notebook format (.ipynb)

## Implementation Steps

### Step 1: Create Directory Structure (2 minutes)

```bash
# From repository root
mkdir -p examples/notebooks
mkdir -p examples/test_database
mkdir -p examples/shared
```

### Step 2: Set Up Test Database (10 minutes)

**Create** `examples/test_database/schema.sql`:
- Copy from `specs/002-example-notebooks/contracts/test_database_schema.sql`
- Adjust for target database (SQLite recommended for portability)

**Create** `examples/test_database/setup.py`:
```python
#!/usr/bin/env python3
"""Setup script for DBMCP example test database."""
import sqlite3
from pathlib import Path

def setup_database(db_path: str = "examples/test_database/example.db"):
    """Create and populate test database from schema.sql"""
    schema_path = Path(__file__).parent / "schema.sql"

    # Remove existing database
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()

    # Create new database and execute schema
    conn = sqlite3.connect(db_path)
    with open(schema_path, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    print(f"✓ Test database created at {db_path}")

if __name__ == "__main__":
    setup_database()
```

**Test it**:
```bash
python examples/test_database/setup.py
# Should create examples/test_database/example.db
```

### Step 3: Create Shared Helpers (15 minutes)

**Create** `examples/shared/notebook_helpers.py`:
```python
"""Shared utilities for DBMCP example notebooks."""
import os
import sys
from pathlib import Path
from typing import Optional

def setup_connection(connection_string: Optional[str] = None):
    """
    Establish DBMCP connection with fallback to local test database.

    Args:
        connection_string: Optional connection string. If None, uses
                          DBMCP_CONNECTION_STRING env var or local test DB.

    Returns:
        Connected DBMCP connection object

    Raises:
        ConnectionError: If connection fails with helpful message
    """
    if connection_string is None:
        connection_string = os.getenv(
            "DBMCP_CONNECTION_STRING",
            "sqlite:///examples/test_database/example.db"
        )

    try:
        # Import DBMCP connection logic
        from src.db.connection import ConnectionManager

        manager = ConnectionManager()
        connection = manager.create_connection(connection_string)
        return connection

    except ImportError as e:
        raise ConnectionError(
            f"DBMCP not importable: {e}\n"
            "Ensure you're running from repository root and DBMCP is installed."
        )
    except Exception as e:
        raise ConnectionError(
            f"Connection failed: {e}\n"
            f"Connection string: {connection_string}\n"
            "Check connection details and database availability."
        )

def print_table(rows: list, headers: list, max_rows: int = 20) -> None:
    """
    Print query results as formatted ASCII table.

    Args:
        rows: List of row tuples/lists
        headers: Column headers
        max_rows: Maximum rows to display (rest shown as "...")
    """
    if not rows:
        print("(No rows returned)")
        return

    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in rows[:max_rows]:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    # Print header
    header_line = " | ".join(
        str(h).ljust(w) for h, w in zip(headers, col_widths)
    )
    print(header_line)
    print("-" * len(header_line))

    # Print rows
    for row in rows[:max_rows]:
        print(" | ".join(
            str(val).ljust(w) for val, w in zip(row, col_widths)
        ))

    if len(rows) > max_rows:
        print(f"... ({len(rows) - max_rows} more rows)")

    print(f"\nTotal: {len(rows)} rows")

def verify_notebook_environment() -> bool:
    """
    Check that notebook environment has required dependencies.

    Returns:
        True if all dependencies available, False otherwise
    """
    missing = []

    # Check critical imports
    try:
        import mcp
    except ImportError:
        missing.append("mcp (install: pip install mcp[cli])")

    try:
        import sqlalchemy
    except ImportError:
        missing.append("sqlalchemy (install: pip install sqlalchemy)")

    # Check test database
    test_db = Path("examples/test_database/example.db")
    if not test_db.exists():
        missing.append(
            "test database (run: python examples/test_database/setup.py)"
        )

    if missing:
        print("⚠️ Missing dependencies:")
        for item in missing:
            print(f"  - {item}")
        return False

    print("✓ All dependencies available")
    return True
```

### Step 4: Create Basic Notebook (30 minutes)

**Create** `examples/notebooks/01_basic_connection.ipynb`:

Use Jupyter to create notebook with this structure:
1. Title and metadata cell (markdown)
2. Overview and prerequisites (markdown)
3. Environment verification (code)
4. Section 1: Connection setup (markdown + code + explanation)
5. Section 2: List schemas (markdown + code + explanation)
6. Section 3: List tables (markdown + code + explanation)
7. Summary (markdown)
8. Next steps (markdown)

**Follow contract**: See `specs/002-example-notebooks/contracts/notebook_structure.md`

**Start Jupyter**:
```bash
jupyter notebook examples/notebooks/
```

**Key content for basic notebook**:
- Demonstrate `connect_database` operation
- Show `list_schemas` with result formatting
- Show `list_tables` with filtering options
- Keep it simple - ~10-12 cells total
- Execute all cells and save with outputs

### Step 5: Create Intermediate Notebook (45 minutes)

**Create** `examples/notebooks/02_table_inspection.ipynb`:

Focus on deeper schema exploration:
- `get_table_schema` with full details
- Column information and constraints
- Index inspection
- `infer_relationships` introduction
- Show confidence scores and reasoning

**~15-18 cells total**. Execute and save with outputs.

### Step 6: Create Advanced Notebook (60 minutes)

**Create** `examples/notebooks/03_advanced_patterns.ipynb`:

Cover power user features:
- Filtering large result sets (parameters)
- Connection configuration options
- Error handling demonstrations (try/except pattern)
- Performance optimization (summary vs detailed mode)
- Real-world workflow example

**~20-25 cells total**. Execute and save with outputs.

### Step 7: Create Index README (20 minutes)

**Create** `examples/README.md`:

```markdown
# DBMCP Examples

Interactive Jupyter notebooks demonstrating DBMCP database exploration capabilities.

## Quick Start

1. **Setup test database**:
   ```bash
   python examples/test_database/setup.py
   ```

2. **Install Jupyter** (if not already installed):
   ```bash
   pip install jupyter notebook
   ```

3. **Launch notebooks**:
   ```bash
   jupyter notebook examples/notebooks/
   ```

4. **Start with**: `01_basic_connection.ipynb`

## Notebooks

| Notebook | Difficulty | Time | Features |
|----------|-----------|------|----------|
| [01_basic_connection.ipynb](notebooks/01_basic_connection.ipynb) | Beginner | 5 min | Connection, list schemas, list tables |
| [02_table_inspection.ipynb](notebooks/02_table_inspection.ipynb) | Intermediate | 10 min | Table details, columns, indexes, relationships |
| [03_advanced_patterns.ipynb](notebooks/03_advanced_patterns.ipynb) | Advanced | 15 min | Filtering, error handling, optimization |

## Using Your Own Database

By default, examples use a local test database. To connect to your own database:

```python
import os
os.environ["DBMCP_CONNECTION_STRING"] = "your-connection-string-here"
```

## Test Database Schema

The test database contains a sample e-commerce schema:
- **customers**: Customer information
- **products**: Product catalog
- **orders**: Customer orders
- **order_items**: Order line items
- **shipping_addresses**: Delivery addresses (undeclared FK for inference demo)
- **product_reviews**: Customer reviews (undeclared FKs for inference demo)

## Prerequisites

- Python 3.11+
- DBMCP installed (`pip install -e .` from repository root)
- Jupyter Notebook or JupyterLab

## Troubleshooting

**Import errors**: Ensure you're running notebooks from repository root and DBMCP is installed in your environment.

**Connection errors**: Verify test database exists by running `python examples/test_database/setup.py` again.

**Missing dependencies**: Run `pip install -r requirements.txt` from repository root.

## Contributing

When updating notebooks:
1. Increment version number in notebook metadata
2. Update "Last Updated" date
3. Re-execute all cells to update outputs
4. Verify notebooks pass: `pytest tests/examples/`
5. Update this README if adding new notebooks

## Need Help?

- 🐛 [Report issues](../../issues)
- 📖 [Documentation](../../docs)
- 💬 [Discussions](../../discussions)
```

### Step 8: Add Tests (30 minutes)

**Create** `tests/examples/test_database_setup.py`:
```python
"""Tests for example database setup."""
import sqlite3
from pathlib import Path
import pytest

def test_database_schema_creates_all_tables():
    """Verify all 6 tables are created."""
    db_path = "examples/test_database/example.db"
    assert Path(db_path).exists(), "Database file should exist"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    expected = [
        'customers', 'order_items', 'orders',
        'product_reviews', 'products', 'shipping_addresses'
    ]
    assert tables == expected

    conn.close()

def test_database_has_sample_data():
    """Verify sample data is populated."""
    db_path = "examples/test_database/example.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check record counts
    cursor.execute("SELECT COUNT(*) FROM customers")
    assert cursor.fetchone()[0] == 10, "Should have 10 customers"

    cursor.execute("SELECT COUNT(*) FROM products")
    assert cursor.fetchone()[0] == 20, "Should have 20 products"

    conn.close()

def test_database_foreign_keys():
    """Verify declared foreign key constraints."""
    db_path = "examples/test_database/example.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check orders table has FK to customers
    cursor.execute("PRAGMA foreign_key_list(orders)")
    fks = cursor.fetchall()
    assert len(fks) == 1, "orders should have 1 FK"
    assert fks[0][2] == 'customers', "FK should reference customers"

    # Check order_items has 2 FKs
    cursor.execute("PRAGMA foreign_key_list(order_items)")
    fks = cursor.fetchall()
    assert len(fks) == 2, "order_items should have 2 FKs"

    conn.close()
```

**Add to pyproject.toml** (optional dependencies):
```toml
[project.optional-dependencies]
examples = [
    "jupyter>=1.0.0",
    "notebook>=7.0.0",
]
```

### Step 9: Update CI (15 minutes)

Add notebook validation to CI pipeline (if applicable):

```yaml
# .github/workflows/test.yml or similar
- name: Test example notebooks
  run: |
    pip install nbval
    pytest --nbval-lax examples/notebooks/
```

### Step 10: Final Verification (10 minutes)

```bash
# 1. Test database setup
python examples/test_database/setup.py

# 2. Run example tests
pytest tests/examples/

# 3. Manually run each notebook
jupyter notebook examples/notebooks/01_basic_connection.ipynb
# Execute all cells, verify outputs

# 4. Check file structure
tree examples/
```

Expected structure:
```
examples/
├── README.md
├── notebooks/
│   ├── 01_basic_connection.ipynb
│   ├── 02_table_inspection.ipynb
│   └── 03_advanced_patterns.ipynb
├── shared/
│   └── notebook_helpers.py
└── test_database/
    ├── example.db
    ├── schema.sql
    └── setup.py
```

## Success Criteria Checklist

- [ ] All 3 notebooks execute successfully ("Run All" works)
- [ ] Basic notebook completes in <5 minutes
- [ ] Test database creates with all 6 tables
- [ ] Helper functions work (imports, connection, formatting)
- [ ] README index accurately describes notebooks
- [ ] Notebooks include version metadata
- [ ] Notebooks saved with pre-executed outputs
- [ ] Tests pass: `pytest tests/examples/`
- [ ] No hardcoded credentials or absolute paths
- [ ] Each notebook demonstrates features from spec

## Common Pitfalls

⚠️ **Notebook paths**: Always use relative paths from repo root
⚠️ **Outputs**: Commit notebooks WITH outputs (don't clear them)
⚠️ **Dependencies**: Test in clean environment to catch missing imports
⚠️ **Database**: SQLite syntax differs from SQL Server (AUTOINCREMENT vs IDENTITY)
⚠️ **Cell execution order**: Notebooks must work top-to-bottom without cell reordering

## Time Estimate

- **Setup & database**: 30 minutes
- **Notebook creation**: 2-3 hours
- **Testing & documentation**: 1 hour
- **Total**: 3-4 hours for experienced developer

## Next Steps After Implementation

1. Create PR with examples
2. Update main project README to link to examples
3. Consider adding notebook screenshots to docs
4. Add "Try the examples" to getting started guide
