# DBMCP Examples

Interactive Jupyter notebooks demonstrating DBMCP database exploration capabilities.

## Quick Start

1. **Setup test database**:
   ```bash
   python3 examples/test_database/setup.py
   ```

2. **Install Jupyter** (if not already installed):
   ```bash
   pip install jupyter notebook
   ```

3. **Launch notebooks**:
   ```bash
   jupyter notebook examples/notebooks/
   ```

   Or open notebooks directly from any location - they automatically detect the repository root!

4. **Start with**: `01_basic_connection.ipynb`

## Notebooks

| Notebook | Difficulty | Time | Features |
|----------|-----------|------|------------|
| [01_basic_connection.ipynb](notebooks/01_basic_connection.ipynb) | Beginner | 5 min | Connection, list schemas, list tables |
| [02_table_inspection.ipynb](notebooks/02_table_inspection.ipynb) | Intermediate | 10 min | Table details, columns, indexes, relationships |
| [03_advanced_patterns.ipynb](notebooks/03_advanced_patterns.ipynb) | Advanced | 15 min | Filtering, error handling, optimization |

## Using Your Own Database

By default, examples use a local test database. To connect to your own database:

```python
import os
os.environ["DBMCP_CONNECTION_STRING"] = "your-connection-string-here"
```

Connection string format:
- **SQLite**: `sqlite:///path/to/database.db`
- **SQL Server**: `mssql+pyodbc://user:password@host/database?driver=ODBC+Driver+17+for+SQL+Server`
- **PostgreSQL**: `postgresql://user:password@host:port/database`
- **MySQL**: `mysql+pymysql://user:password@host:port/database`

## Test Database Schema

The test database contains a sample e-commerce schema:

- **customers** (10 rows): Customer information with email, name, timestamps
- **products** (20 rows): Product catalog with categories, prices, stock levels
- **orders** (15 rows): Customer orders with status tracking
- **order_items** (30 rows): Order line items linking orders to products
- **shipping_addresses** (12 rows): Delivery addresses (undeclared FK for inference demo)
- **product_reviews** (25 rows): Customer reviews (undeclared FKs for inference demo)

**Key Features**:
- ✓ Declared foreign keys on `orders` and `order_items` tables
- ✓ Undeclared relationships on `shipping_addresses` and `product_reviews` (for inference testing)
- ✓ Mix of data types: INTEGER, VARCHAR, DECIMAL, DATETIME, TEXT
- ✓ Constraints: PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK, DEFAULT
- ✓ Realistic data for meaningful exploration

## Prerequisites

- Python 3.11+
- DBMCP installed (`pip install -e .` from repository root)
- SQLAlchemy installed (`pip install sqlalchemy`)
- Jupyter Notebook or JupyterLab

## Troubleshooting

**Import errors**: The notebooks automatically find the repository root, so you can open them from anywhere. Just ensure DBMCP dependencies are installed:

```bash
# Install DBMCP dependencies
pip install -e .

# Verify installation
python3 -c "import sqlalchemy; print('SQLAlchemy:', sqlalchemy.__version__)"
```

**Connection errors**: Verify test database exists by running the setup script:
```bash
python3 examples/test_database/setup.py
```

**Path issues**: The notebooks automatically detect the repository root by looking for `pyproject.toml`. If you've moved files outside the repository structure, set the database path explicitly:
```python
import os
os.environ["DBMCP_CONNECTION_STRING"] = "sqlite:////absolute/path/to/example.db"
```

**Missing dependencies**: Install optional dependencies for examples:
```bash
pip install -e ".[examples]"
```

**Notebook kernel issues**: Make sure Jupyter is using the correct Python environment:
```bash
python3 -m ipykernel install --user --name=dbmcp
# Then select "dbmcp" kernel in Jupyter
```

## Contributing

When updating notebooks:
1. Increment version number in notebook metadata
2. Update "Last Updated" date
3. Re-execute all cells to update outputs
4. Verify notebooks pass: `pytest tests/examples/` (if pytest installed)
5. Update this README if adding new notebooks

## Notebook Structure

All notebooks follow a consistent structure:
1. **Title and Metadata**: Version info, compatibility, difficulty
2. **Overview**: What you'll learn and prerequisites
3. **Environment Verification**: Dependency checks
4. **Content Sections**: Progressive learning with examples
5. **Summary**: Key takeaways and common pitfalls
6. **Next Steps**: Links to related notebooks and resources

## Need Help?

- 🐛 [Report issues](../../issues)
- 📖 [Main Documentation](../../README.md)
- 💬 [Discussions](../../discussions)

## Additional Resources

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Jupyter Notebook Documentation](https://jupyter-notebook.readthedocs.io/)
- [Database Design Patterns](https://en.wikipedia.org/wiki/Database_design)

---

**Note**: These notebooks use SQLite for portability. The patterns demonstrated work with any database supported by SQLAlchemy (SQL Server, PostgreSQL, MySQL, Oracle, etc.). Simply change the connection string to connect to your database.
