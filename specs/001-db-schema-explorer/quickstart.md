# Quickstart: Database Schema Explorer MCP Server

**Feature**: 001-db-schema-explorer
**Date**: 2026-01-19
**Audience**: Developers implementing this MCP server

## Overview

This quickstart guide walks through setting up the Database Schema Explorer MCP server from scratch, implementing core functionality, and testing with Claude for Desktop.

**Time to First Working Tool**: ~2 hours

---

## Prerequisites

- Python 3.11 or higher
- Microsoft ODBC Driver 18 for SQL Server
- Access to a SQL Server database (for testing)
- Claude for Desktop (for testing MCP tools)

---

## Step 1: Environment Setup (10 minutes)

### 1.1 Install Python Dependencies

```bash
# Create project directory
cd /Users/jsmith79/Documents/Projects/Ongoing/dbmcp

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install core dependencies
pip install "mcp[cli]" sqlalchemy pyodbc

# Install testing dependencies
pip install pytest pytest-asyncio pytest-cov
```

### 1.2 Install ODBC Driver

**macOS:**
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql18
```

**Linux (Ubuntu/Debian):**
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/msprod.list
sudo apt-get update
sudo apt-get install msodbcsql18
```

**Windows:**
Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

### 1.3 Verify Installation

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
# Should show: ['ODBC Driver 18 for SQL Server', ...]
```

---

## Step 2: Project Structure (5 minutes)

Create the directory structure per [plan.md](./plan.md):

```bash
mkdir -p src/{mcp_server,db,inference,cache,models}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p docs
touch src/mcp_server/{server.py,tools.py}
touch src/db/{connection.py,metadata.py,query.py}
touch src/inference/{relationships.py,columns.py}
touch src/cache/{storage.py,drift.py}
touch src/models/{schema.py,relationship.py}
```

---

## Step 3: Implement Core Models (15 minutes)

### 3.1 Create Data Classes (`src/models/schema.py`)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Connection:
    connection_id: str
    server: str
    database: str
    port: int = 1433
    username: Optional[str] = None
    created_at: datetime = None

@dataclass
class Schema:
    schema_id: str
    connection_id: str
    schema_name: str
    table_count: int
    view_count: int
    last_scanned: datetime

@dataclass
class Table:
    table_id: str
    schema_id: str
    table_name: str
    table_type: str
    row_count: Optional[int]
    has_primary_key: bool
    access_denied: bool = False

@dataclass
class Column:
    column_id: str
    table_id: str
    column_name: str
    ordinal_position: int
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
```

### 3.2 Create Relationship Model (`src/models/relationship.py`)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class InferredFK:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    confidence: float
    reasoning: str
    relationship_type: str = "inferred"  # or "declared"
```

---

## Step 4: Implement Database Connection (20 minutes)

### 4.1 Connection Manager (`src/db/connection.py`)

```python
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from src.models.schema import Connection
import hashlib
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.engines = {}  # connection_id → engine

    def connect(
        self,
        server: str,
        database: str,
        username: str,
        password: str,
        port: int = 1433,
        trust_server_cert: bool = False,
        connection_timeout: int = 30
    ) -> Connection:
        """Create database connection and return Connection object."""

        # Generate connection ID (hash excludes password)
        conn_str_hash = f"{server}:{port}/{database}/{username}"
        connection_id = hashlib.sha256(conn_str_hash.encode()).hexdigest()[:12]

        # Build ODBC connection string
        odbc_conn_str = (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={server},{port};"
            f"Database={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate={'yes' if trust_server_cert else 'no'};"
            f"Connection Timeout={connection_timeout};"
        )

        # Create SQLAlchemy engine with connection pooling
        engine = create_engine(
            f"mssql+pyodbc:///?odbc_connect={odbc_conn_str}",
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Validate connections before use
            echo=False  # Set True for SQL debugging
        )

        # Test connection
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT @@VERSION"))
                version = result.scalar()
                logger.info(f"Connected to: {version}")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

        # Store engine
        self.engines[connection_id] = engine

        return Connection(
            connection_id=connection_id,
            server=server,
            database=database,
            port=port,
            username=username
        )

    def get_engine(self, connection_id: str):
        """Get SQLAlchemy engine for connection ID."""
        if connection_id not in self.engines:
            raise ValueError(f"Connection {connection_id} not found")
        return self.engines[connection_id]
```

---

## Step 5: Implement Metadata Queries (25 minutes)

### 5.1 Metadata Service (`src/db/metadata.py`)

```python
from sqlalchemy import inspect, text
from src.models.schema import Schema, Table, Column
from typing import List
import logging

logger = logging.getLogger(__name__)

class MetadataService:
    def __init__(self, engine):
        self.engine = engine
        self.inspector = inspect(engine)

    def list_schemas(self) -> List[Schema]:
        """List all schemas with table/view counts."""
        schemas = []

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    s.name AS schema_name,
                    COUNT(DISTINCT CASE WHEN t.type = 'U' THEN t.name END) AS table_count,
                    COUNT(DISTINCT CASE WHEN t.type = 'V' THEN t.name END) AS view_count
                FROM sys.schemas s
                LEFT JOIN sys.tables t ON s.schema_id = t.schema_id
                GROUP BY s.name
                ORDER BY table_count DESC
            """))

            for row in result:
                schemas.append(Schema(
                    schema_id=f"schema_{row.schema_name}",
                    connection_id="",  # Set by caller
                    schema_name=row.schema_name,
                    table_count=row.table_count or 0,
                    view_count=row.view_count or 0,
                    last_scanned=None
                ))

        return schemas

    def list_tables(self, schema_name: str = None) -> List[Table]:
        """List tables in schema(s)."""
        tables = []

        # Get table names from inspector
        if schema_name:
            table_names = self.inspector.get_table_names(schema=schema_name)
        else:
            # Get all schemas
            all_tables = []
            for schema in self.inspector.get_schema_names():
                all_tables.extend([
                    (schema, t) for t in self.inspector.get_table_names(schema=schema)
                ])
            table_names = all_tables

        # Get row counts efficiently
        with self.engine.connect() as conn:
            for item in table_names:
                if isinstance(item, tuple):
                    schema, table = item
                else:
                    schema = schema_name or 'dbo'
                    table = item

                # Check if table has PK
                pk = self.inspector.get_pk_constraint(table, schema=schema)
                has_pk = len(pk.get('constrained_columns', [])) > 0

                # Get row count (fast via DMV)
                try:
                    result = conn.execute(text(f"""
                        SELECT SUM(p.rows) AS row_count
                        FROM sys.tables t
                        INNER JOIN sys.partitions p ON t.object_id = p.object_id
                        WHERE t.name = '{table}' AND p.index_id IN (0,1)
                    """))
                    row_count = result.scalar() or 0
                except:
                    row_count = None

                tables.append(Table(
                    table_id=f"{schema}.{table}",
                    schema_id=schema,
                    table_name=table,
                    table_type='table',
                    row_count=row_count,
                    has_primary_key=has_pk,
                    access_denied=False
                ))

        return tables

    def get_table_schema(self, table_name: str, schema_name: str = 'dbo') -> dict:
        """Get detailed table schema."""
        columns = self.inspector.get_columns(table_name, schema=schema_name)
        indexes = self.inspector.get_indexes(table_name, schema=schema_name)
        fks = self.inspector.get_foreign_keys(table_name, schema=schema_name)
        pk = self.inspector.get_pk_constraint(table_name, schema=schema_name)

        # Mark PK columns
        pk_columns = set(pk.get('constrained_columns', []))

        column_list = []
        for col in columns:
            column_list.append({
                'column_name': col['name'],
                'data_type': str(col['type']),
                'is_nullable': col['nullable'],
                'default': col.get('default'),
                'is_primary_key': col['name'] in pk_columns
            })

        return {
            'table_name': table_name,
            'schema_name': schema_name,
            'columns': column_list,
            'indexes': indexes,
            'foreign_keys': fks
        }
```

---

## Step 6: Implement FastMCP Server (30 minutes)

### 6.1 MCP Server (`src/mcp_server/server.py`)

```python
from mcp.server.fastmcp import FastMCP
from src.db.connection import ConnectionManager
from src.db.metadata import MetadataService
import logging

# Configure logging (NEVER use print() - corrupts JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('dbmcp.log'), logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("dbmcp")

# Global connection manager
conn_manager = ConnectionManager()

@mcp.tool()
async def connect_database(
    server: str,
    database: str,
    username: str,
    password: str,
    port: int = 1433,
    trust_server_cert: bool = False
) -> str:
    """Connect to a SQL Server database.

    Args:
        server: SQL Server host (hostname or IP)
        database: Database name
        username: Username for authentication
        password: Password for authentication
        port: SQL Server port (default: 1433)
        trust_server_cert: Trust server certificate (default: False)

    Returns:
        JSON string with connection details
    """
    try:
        connection = conn_manager.connect(
            server=server,
            database=database,
            username=username,
            password=password,
            port=port,
            trust_server_cert=trust_server_cert
        )

        # Get schema count
        engine = conn_manager.get_engine(connection.connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas()

        return {
            "connection_id": connection.connection_id,
            "status": "connected",
            "message": f"Successfully connected to {database}",
            "schema_count": len(schemas)
        }

    except Exception as e:
        logger.error(f"Connection error: {e}")
        return {
            "status": "failed",
            "message": str(e)
        }

@mcp.tool()
async def list_schemas(connection_id: str) -> str:
    """List all schemas in the database.

    Args:
        connection_id: Connection ID from connect_database

    Returns:
        JSON string with schema list
    """
    try:
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas()

        return {
            "schemas": [
                {
                    "schema_name": s.schema_name,
                    "table_count": s.table_count,
                    "view_count": s.view_count
                }
                for s in schemas
            ],
            "total_schemas": len(schemas)
        }

    except Exception as e:
        logger.error(f"Error listing schemas: {e}")
        return {"error": str(e)}

@mcp.tool()
async def list_tables(
    connection_id: str,
    schema_name: str = None,
    limit: int = 100
) -> str:
    """List tables in specified schema(s).

    Args:
        connection_id: Connection ID from connect_database
        schema_name: Schema name (optional, default: all schemas)
        limit: Maximum tables to return (default: 100)

    Returns:
        JSON string with table list
    """
    try:
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)
        tables = metadata_svc.list_tables(schema_name=schema_name)

        # Apply limit
        tables = tables[:limit]

        return {
            "tables": [
                {
                    "schema_name": t.schema_id,
                    "table_name": t.table_name,
                    "row_count": t.row_count,
                    "has_primary_key": t.has_primary_key
                }
                for t in tables
            ],
            "total_tables": len(tables)
        }

    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return {"error": str(e)}

@mcp.tool()
async def get_table_schema(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo"
) -> str:
    """Get detailed schema for a table.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Table name
        schema_name: Schema name (default: dbo)

    Returns:
        JSON string with table schema details
    """
    try:
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)
        schema = metadata_svc.get_table_schema(table_name, schema_name)

        return {"table": schema}

    except Exception as e:
        logger.error(f"Error getting table schema: {e}")
        return {"error": str(e)}

def main():
    """Run MCP server on stdio transport."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

---

## Step 7: Test Locally (15 minutes)

### 7.1 Create Test Script (`test_manual.py`)

```python
import asyncio
from src.mcp_server.server import connect_database, list_schemas, list_tables

async def test_connection():
    # Update with your SQL Server credentials
    result = await connect_database(
        server="localhost",
        database="AdventureWorks",
        username="sa",
        password="YourPassword"
    )
    print("Connection result:", result)

    if result.get("status") == "connected":
        connection_id = result["connection_id"]

        # List schemas
        schemas = await list_schemas(connection_id)
        print("\nSchemas:", schemas)

        # List tables
        tables = await list_tables(connection_id, limit=10)
        print("\nTables:", tables)

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run test:
```bash
python test_manual.py
```

---

## Step 8: Configure Claude for Desktop (10 minutes)

### 8.1 Update Claude Config

Edit `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "python",
      "args": [
        "-m",
        "src.mcp_server.server"
      ],
      "cwd": "/Users/jsmith79/Documents/Projects/Ongoing/dbmcp",
      "env": {
        "PYTHONPATH": "/Users/jsmith79/Documents/Projects/Ongoing/dbmcp"
      }
    }
  }
}
```

### 8.2 Restart Claude for Desktop

Quit and reopen Claude for Desktop. The `dbmcp` server should appear in the MCP servers list.

---

## Step 9: Test with Claude (10 minutes)

Open Claude for Desktop and try:

```
Connect to my SQL Server database at localhost, database AdventureWorks,
username sa, password YourPassword.

Then list all schemas and show me the top 10 tables by row count.
```

Claude should invoke your MCP tools and display the results.

---

## Next Steps

1. **Implement Relationship Inference** (Phase 1):
   - Follow guide in `/research/FK_INFERENCE_IMPLEMENTATION_CHECKLIST.md`
   - Reference implementation: `/research/fk_inference_phase1_example.py`

2. **Add Sample Data Tool**:
   - Implement `get_sample_data` tool per [contracts/mcp_tools.md](./contracts/mcp_tools.md)

3. **Add Column Analysis**:
   - Implement `analyze_column` tool for purpose inference

4. **Add Caching**:
   - Implement documentation export and caching per [data-model.md](./data-model.md)

5. **Write Tests**:
   - Unit tests for inference algorithms
   - Integration tests with test database

---

## Troubleshooting

**Issue**: "No module named 'mcp'"
- **Fix**: Ensure `mcp[cli]` is installed: `pip install "mcp[cli]"`

**Issue**: "pyodbc.Error: Data source name not found"
- **Fix**: Install ODBC Driver 18 (see Step 1.2)

**Issue**: Claude doesn't see the tools
- **Fix**: Check `claude_desktop_config.json` path is correct and restart Claude

**Issue**: Connection timeout
- **Fix**: Check SQL Server is reachable and firewall allows port 1433

---

## Resources

- [MCP Documentation](https://modelcontextprotocol.io)
- [FastMCP Guide](https://modelcontextprotocol.io/quickstart/server)
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [SQLAlchemy SQL Server Dialect](https://docs.sqlalchemy.org/en/20/dialects/mssql.html)
- [Project Research](./research.md)
- [Data Model](./data-model.md)
- [MCP Tool Contracts](./contracts/mcp_tools.md)
