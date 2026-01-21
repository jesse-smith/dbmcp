# dbmcp Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-19

## Active Technologies
- Python 3.11+ (matching main project) + Jupyter/IPython (notebook environment), existing DBMCP dependencies (mcp[cli], sqlalchemy, pyodbc) (002-example-notebooks)
- File-based (.ipynb files), test database schema (SQL scripts) (002-example-notebooks)

- Python 3.11+ + FastMCP (MCP SDK), pyodbc (SQL Server driver), SQLAlchemy (connection pooling + metadata introspection) (001-db-schema-explorer)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+: Follow standard conventions

## Recent Changes
- 002-example-notebooks: Added Python 3.11+ (matching main project) + Jupyter/IPython (notebook environment), existing DBMCP dependencies (mcp[cli], sqlalchemy, pyodbc)

- 001-db-schema-explorer: Added Python 3.11+ + FastMCP (MCP SDK), pyodbc (SQL Server driver), SQLAlchemy (connection pooling + metadata introspection)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
