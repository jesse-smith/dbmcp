"""Data models for database schema entities.

These models represent the core entities used by the Database Schema Explorer MCP server.
All entities are internal data structures - no persistent database storage required.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AuthenticationMethod(StrEnum):
    """Supported authentication methods for SQL Server connections."""

    SQL = "sql"
    WINDOWS = "windows"
    AZURE_AD = "azure_ad"
    AZURE_AD_INTEGRATED = "azure_ad_integrated"


@dataclass
class ResolvedConnectionParams:
    """Effective connection parameters after merging config + explicit args."""

    server: str
    database: str
    port: int
    authentication_method: str
    trust_server_cert: bool
    connection_timeout: int
    username: str | None
    password: str | None
    tenant_id: str | None


class TableType(StrEnum):
    """Database object types."""

    TABLE = "table"
    VIEW = "view"


class SamplingMethod(StrEnum):
    """Methods for sampling table data."""

    TOP = "top"  # Simple SELECT TOP N (fast, not representative)
    TABLESAMPLE = "tablesample"  # SQL Server TABLESAMPLE (statistical)
    MODULO = "modulo"  # WHERE ID % interval = 0 (deterministic)


class QueryType(StrEnum):
    """SQL query types."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    OTHER = "other"


class DenialCategory(StrEnum):
    """Classification of why a query was denied."""

    DML = "dml"
    DDL = "ddl"
    DCL = "dcl"
    OPERATIONAL = "operational"
    STORED_PROCEDURE = "stored_procedure"
    SELECT_INTO = "select_into"
    CTE_WRAPPED_WRITE = "cte_wrapped_write"
    PARSE_FAILURE = "parse_failure"


@dataclass
class DenialReason:
    """A single reason why a query (or statement within a batch) was denied."""

    category: DenialCategory
    detail: str
    statement_index: int = 0


@dataclass
class ValidationResult:
    """Outcome of query validation."""

    is_safe: bool
    reasons: list[DenialReason] = field(default_factory=list)


@dataclass
class Connection:
    """Represents a database connection configuration.

    Attributes:
        connection_id: Unique identifier (hash of server+database+user)
        server: SQL Server host (hostname or IP)
        database: Database name
        port: Port number (default: 1433)
        authentication_method: Authentication method used
        username: Username for SQL/Azure AD auth
        created_at: Connection creation timestamp
    """

    connection_id: str
    server: str
    database: str
    port: int = 1433
    authentication_method: AuthenticationMethod = AuthenticationMethod.SQL
    username: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # Note: password is NEVER stored in this model (NFR-005 compliance)


@dataclass
class Schema:
    """A namespace grouping of database objects.

    Attributes:
        schema_id: Unique identifier (connection_id + schema_name)
        connection_id: Parent connection ID
        schema_name: Schema name (e.g., 'dbo', 'sales')
        table_count: Number of tables in schema
        view_count: Number of views in schema
        last_scanned: Last metadata scan timestamp
    """

    schema_id: str
    connection_id: str
    schema_name: str
    table_count: int = 0
    view_count: int = 0
    last_scanned: datetime | None = None


@dataclass
class Table:
    """A database table with columns, indexes, and relationships.

    Attributes:
        table_id: Unique identifier (schema_id + table_name)
        schema_id: Parent schema ID
        table_name: Table name
        table_type: Type of object (table or view)
        row_count: Approximate row count (None if inaccessible)
        row_count_updated: When row count was last updated
        has_primary_key: Whether table has a primary key
        last_modified: Last DDL modification timestamp
        access_denied: True if user lacks SELECT permission
    """

    table_id: str
    schema_id: str
    table_name: str
    table_type: TableType = TableType.TABLE
    row_count: int | None = None
    row_count_updated: datetime | None = None
    has_primary_key: bool = False
    last_modified: datetime | None = None
    access_denied: bool = False


@dataclass
class Column:
    """A table column with metadata.

    Attributes:
        column_id: Unique identifier (table_id + column_name)
        table_id: Parent table ID
        column_name: Column name
        ordinal_position: Column position in table (1-based)
        data_type: SQL Server data type (e.g., 'INT', 'VARCHAR(50)')
        max_length: Max length for strings/binary
        is_nullable: Whether NULL values are allowed
        default_value: Default value expression
        is_identity: Whether auto-increment identity
        is_computed: Whether computed column
        is_primary_key: Whether part of primary key
        is_foreign_key: Whether declared as foreign key
    """

    column_id: str
    table_id: str
    column_name: str
    ordinal_position: int
    data_type: str
    max_length: int | None = None
    is_nullable: bool = True
    default_value: str | None = None
    is_identity: bool = False
    is_computed: bool = False
    is_primary_key: bool = False
    is_foreign_key: bool = False


@dataclass
class Index:
    """A database index on one or more columns.

    Attributes:
        index_id: Unique identifier (table_id + index_name)
        table_id: Parent table ID
        index_name: Index name
        is_unique: Whether unique constraint
        is_primary_key: Whether primary key constraint
        is_clustered: Whether clustered index
        columns: Ordered list of column names (key columns)
        included_columns: Non-key included columns
    """

    index_id: str
    table_id: str
    index_name: str
    is_unique: bool = False
    is_primary_key: bool = False
    is_clustered: bool = False
    columns: list[str] = field(default_factory=list)
    included_columns: list[str] = field(default_factory=list)


@dataclass
class Query:
    """A SQL query submitted for execution.

    Attributes:
        query_id: Unique identifier (UUID)
        connection_id: Connection to execute on
        query_text: SQL query text
        query_type: Parsed query type
        is_allowed: Whether execution is permitted
        row_limit: Max rows to return
        execution_time_ms: Query execution time (if executed)
        rows_affected: Rows returned/affected (if executed)
        error_message: Error if query failed
        executed_at: When query was executed
    """

    query_id: str
    connection_id: str
    query_text: str
    query_type: QueryType = QueryType.SELECT
    is_allowed: bool = True
    row_limit: int = 1000
    execution_time_ms: int | None = None
    rows_affected: int | None = None
    error_message: str | None = None
    executed_at: datetime | None = None
    denial_reasons: list[DenialReason] | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    total_rows_available: int | None = None


@dataclass
class SampleData:
    """Sample rows from a table.

    Attributes:
        sample_id: Unique identifier (table_id + timestamp)
        table_id: Source table ID
        sample_size: Number of rows requested
        sampling_method: How rows were sampled
        rows: Array of row objects (column -> value)
        truncated_columns: Columns with truncated values
        sampled_at: When sample was taken
    """

    sample_id: str
    table_id: str
    sample_size: int = 5
    sampling_method: SamplingMethod = SamplingMethod.TOP
    rows: list[dict] = field(default_factory=list)
    truncated_columns: list[str] = field(default_factory=list)
    sampled_at: datetime = field(default_factory=datetime.now)
