# Technology Stack: Multi-Dialect Support Additions

**Project:** dbmcp v2.0
**Researched:** 2026-04-13
**Scope:** New dependencies for Databricks and generic SQLAlchemy dialect support only

## Existing Stack (Validated, Not Changing)

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | >=3.11 | Runtime |
| mcp[cli] | >=1.27.0 | MCP server framework |
| sqlalchemy | >=2.0.0 | Database abstraction, Inspector API |
| pyodbc | >=5.0.0 | SQL Server DBAPI driver |
| sqlglot | >=30.4.2,<31.0.0 | Query parsing, validation, transpilation |
| azure-identity | >=1.14.0 | Azure AD auth for SQL Server |
| toon-format | v0.9.0-beta.1 | Token-efficient response serialization |

## New Dependencies for Databricks

### Required Additions

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| databricks-sqlalchemy | >=2.0.0 | SQLAlchemy dialect for Databricks | Registers `databricks://` dialect with SQLAlchemy, implements all Inspector methods needed by dbmcp (get_schema_names, get_table_names, get_columns, get_pk_constraint, get_foreign_keys). Requires SQLAlchemy >=2.0.21 (compatible with our >=2.0.0 pin). |
| databricks-sql-connector | >=4.0.0 | Databricks SQL DBAPI driver | Required by databricks-sqlalchemy. Provides the actual wire protocol for Databricks SQL warehouses and clusters. Since v4.0.0, SQLAlchemy support was extracted to separate package. |

### NOT Adding (Generic Dialect)

No new packages needed for generic SQLAlchemy dialect support. Any database with a SQLAlchemy dialect + sqlglot dialect can work through the existing stack. Users install their own driver packages (e.g., `psycopg2` for PostgreSQL, `mysql-connector-python` for MySQL) and pass a `sqlalchemy_url` directly.

## Databricks Package Details

### databricks-sqlalchemy 2.0.9

**Confidence:** HIGH (verified via PyPI, GitHub source, and local sqlglot testing)

- **Dialect name:** `"databricks"` (registered as SQLAlchemy entry point)
- **Connection URI:** `databricks://token:{access_token}@{host}?http_path={path}&catalog={catalog}&schema={schema}`
- **Inherits:** `sqlalchemy.engine.default.DefaultDialect`
- **Python support:** 3.8-3.13 (covers our >=3.11 requirement)
- **SQLAlchemy requirement:** >=2.0.21 (compatible with our >=2.0.0 floor)
- **DBR requirement:** 14.2+ for parameterized query support; Unity Catalog enabled

### databricks-sql-connector 4.2.5

**Confidence:** HIGH (verified via PyPI, GitHub source)

- **Transitive dependencies (heavy):** thrift, pandas, lz4, requests, oauthlib, openpyxl, urllib3, python-dateutil, pyjwt, pybreaker
- **Pandas is mandatory:** Required at install time (not optional). Open issue #489 and PR #536 to make it optional, not merged as of April 2026.
- **Package size:** ~214 KB wheel, but transitive deps add significant footprint (pandas alone ~40MB)
- **Authentication:** Token (via URL), OAuth M2M (via connect_args), OAuth U2M (via connect_args)

### Dependency Footprint Warning

databricks-sql-connector pulls in pandas as a mandatory dependency. This adds ~40MB+ to the install. However:
1. dbmcp never imports or uses pandas directly -- it is only a transitive dependency of the connector
2. The connector team has an open PR (#536) to make pandas optional
3. This weight is only imposed on users who install the `databricks` extra, not core users

## sqlglot Databricks Dialect Coverage

**Confidence:** HIGH (verified by running sqlglot 30.4.2 locally)

### What Works

| Feature | Status | Verified |
|---------|--------|----------|
| `dialect="databricks"` string resolution | Works | Local test |
| Parse SELECT/INSERT/UPDATE/DELETE/CREATE/DROP | Correct AST types | Local test |
| Transpile TSQL -> Databricks (TOP -> LIMIT) | Works | Local test |
| Transpile Databricks -> TSQL (LIMIT -> TOP) | Works | Local test |
| Existing denylist validation (DML/DDL/DCL checks) | Works unchanged | Local test -- same AST expression types |
| DESCRIBE TABLE EXTENDED parsing | Parses as `exp.Describe` | Local test |
| Databricks class inherits from Spark | Confirmed | `Databricks.__bases__ == (Spark,)` |

### Databricks Dialect Specifics

- Inherits from `sqlglot.dialects.spark.Spark`
- Adds Databricks-specific functions: GETDATE(), DATEADD, DATEDIFF, UNIFORM()
- Colon operator (`:`) for JSON extraction
- `VOID` type mapping for NULL
- Strict casting enabled

### Integration with Existing Validation

The current `validate_query()` in `src/db/validation.py` hardcodes `dialect="tsql"`. For multi-dialect support, this needs to accept a dialect parameter. The denylist AST types (Insert, Create, Drop, etc.) are dialect-independent -- sqlglot produces the same expression types regardless of dialect. Only the parse dialect string changes.

**Key finding:** The SAFE_PROCEDURES allowlist (22 SQL Server-specific sp_ names) is MSSQL-only. Databricks has no stored procedures in this sense. The validation module needs dialect-aware procedure handling -- likely the DialectStrategy should provide the safe procedure list (empty for Databricks, existing list for MSSQL).

## SQLAlchemy Inspector API Coverage (databricks-sqlalchemy)

**Confidence:** HIGH (verified via GitHub source code review)

### Inspector Methods Used by dbmcp

| Inspector Method | Supported | Implementation Notes |
|-----------------|-----------|---------------------|
| `get_schema_names()` | YES | Uses `SHOW SCHEMAS` |
| `get_table_names()` | YES | Uses `SHOW TABLES FROM {schema}`, filters out views |
| `get_columns()` | YES | Uses `cursor.columns()` with catalog/schema/table params |
| `get_pk_constraint()` | YES | Uses `DESCRIBE TABLE EXTENDED`, parses output |
| `get_foreign_keys()` | YES | Uses `DESCRIBE TABLE EXTENDED`, parses output |
| `get_indexes()` | STUB | Returns empty list (Databricks has no indexes) |
| `get_view_names()` | YES | Not currently used by dbmcp but available |
| `get_table_comment()` | YES | Not currently used by dbmcp but available |
| `has_table()` | YES | Useful for validation |

### Key Behavioral Differences from MSSQL

1. **No indexes:** `get_indexes()` always returns `[]` -- this is correct, not a bug
2. **DESCRIBE TABLE EXTENDED:** Primary metadata strategy (vs information_schema for MSSQL)
3. **No transactions:** `do_rollback()` is a no-op
4. **Table/view conflation:** `SHOW TABLES` returns both; dialect filters by comparing against `get_view_names()`
5. **FK/PK may be sparse:** Databricks tables often lack explicit constraints (especially Delta tables). The Inspector methods return empty results, not errors. This is normal and the analysis tools (find_pk_candidates, find_fk_candidates) provide heuristic alternatives.
6. **Catalog-scoped schemas:** Databricks uses three-level naming (catalog.schema.table). The `catalog` parameter in the connection URI sets the default catalog.

## pyproject.toml Optional Dependencies Structure

**Confidence:** HIGH (standard Python packaging, PEP 508)

### Recommended Structure

Move dialect-specific drivers to optional extras. Core dependencies remain dialect-agnostic:

```toml
[project]
dependencies = [
    "mcp[cli]>=1.27.0",
    "sqlalchemy>=2.0.21",   # Bump floor to match databricks-sqlalchemy requirement
    "sqlglot>=30.4.2,<31.0.0",
    "toon-format @ git+https://github.com/toon-format/toon-python.git@v0.9.0-beta.1",
]

[project.optional-dependencies]
mssql = [
    "pyodbc>=5.0.0",
    "azure-identity>=1.14.0",
]
databricks = [
    "databricks-sqlalchemy>=2.0.0",
    "databricks-sql-connector>=4.0.0",
]
all = [
    "dbmcp[mssql]",
    "dbmcp[databricks]",
]
examples = [
    "jupyter>=1.0.0",
    "notebook>=7.0.0",
]
```

### Key Design Decisions

1. **pyodbc moves to `mssql` extra:** Currently a core dependency. Moving it to an extra means users who only want Databricks don't install pyodbc (which requires ODBC drivers on the system).

2. **azure-identity moves to `mssql` extra:** Only needed for SQL Server Azure AD auth.

3. **SQLAlchemy floor bump to >=2.0.21:** databricks-sqlalchemy requires this minimum. Safe bump since we already require >=2.0.0 and the installed version is 2.0.49.

4. **Self-referencing extras:** `all = ["dbmcp[mssql]", "dbmcp[databricks]"]` is valid PEP 508 and works with pip and uv.

5. **No `generic` extra:** Generic dialect support uses only core deps (SQLAlchemy + sqlglot). Users install their own DBAPI driver independently.

### Installation Commands

```bash
# SQL Server only (current behavior)
uv pip install dbmcp[mssql]

# Databricks only
uv pip install dbmcp[databricks]

# Everything
uv pip install dbmcp[all]

# Development (gets everything)
uv sync --all-extras
```

## Databricks Authentication Strategy

**Confidence:** MEDIUM (verified URL format and connect_args mechanism; OAuth via connect_args not directly tested)

### Supported Auth Methods

| Method | Mechanism | Config |
|--------|-----------|--------|
| Personal Access Token | URL password field | `databricks://token:{token}@{host}?...` |
| OAuth M2M (Service Principal) | connect_args to DBAPI | `create_engine(url, connect_args={"credentials_provider": ...})` |
| OAuth U2M (Interactive) | connect_args to DBAPI | `create_engine(url, connect_args={"auth_type": "databricks-oauth"})` |

The databricks-sqlalchemy dialect's `create_connect_args()` only extracts token from the URL. For OAuth/M2M, the standard SQLAlchemy `connect_args` parameter on `create_engine()` passes additional kwargs directly to the DBAPI `connect()` call, bypassing the dialect's `create_connect_args()`. This is standard SQLAlchemy behavior and does not require dialect modification.

### TOML Config Model for Databricks

```toml
[connections.my_databricks]
dialect = "databricks"
host = "${DATABRICKS_SERVER_HOSTNAME}"
http_path = "${DATABRICKS_HTTP_PATH}"
access_token = "${DATABRICKS_TOKEN}"
catalog = "my_catalog"
schema = "my_schema"
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Databricks dialect | databricks-sqlalchemy | Raw databricks-sql-connector + custom dialect | databricks-sqlalchemy provides all Inspector methods out of box; writing a custom dialect is unnecessary work |
| Databricks DBAPI | databricks-sql-connector | pyhive/thrift | databricks-sql-connector is the official driver, actively maintained, supports latest Databricks features |
| Query transpilation | sqlglot (existing) | Manual SQL rewriting | sqlglot already supports Databricks dialect at our pinned version; no new dependency needed |
| Generic dialect | No new package | Create adapter packages per DB | SQLAlchemy's Inspector API is the adapter; users bring their own driver |

## What NOT to Add

1. **No new query validation library:** sqlglot's Databricks dialect handles parsing and validation identically to TSQL (same AST types).
2. **No Databricks SDK:** `databricks-sdk` is for workspace management, not SQL queries. Unnecessary.
3. **No pyarrow explicit dependency:** databricks-sql-connector includes optional pyarrow support but it is not required for our use case (we use SQLAlchemy result sets, not Arrow).
4. **No alembic:** databricks-sqlalchemy has optional alembic support. We do read-only operations; schema migration is out of scope.
5. **No pandas dependency:** It comes transitively via databricks-sql-connector. Never import it directly.

## Sources

- PyPI: databricks-sql-connector 4.2.5 (https://pypi.org/project/databricks-sql-connector/) -- HIGH confidence
- PyPI: databricks-sqlalchemy 2.0.9 (https://pypi.org/project/databricks-sqlalchemy/) -- HIGH confidence
- GitHub: databricks-sqlalchemy base.py source (https://github.com/databricks/databricks-sqlalchemy/) -- HIGH confidence
- Local verification: sqlglot 30.4.2 Databricks dialect parsing and transpilation -- HIGH confidence
- Databricks docs: SQL connector auth (https://docs.databricks.com/en/dev-tools/python-sql-connector.html) -- HIGH confidence
- Databricks docs: SQLAlchemy usage (https://docs.databricks.com/en/dev-tools/sqlalchemy.html) -- HIGH confidence
- GitHub issue #489: pandas optional dependency status (https://github.com/databricks/databricks-sql-python/issues/489) -- HIGH confidence
