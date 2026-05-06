# Phase 11: DatabricksDialect - Research

**Researched:** 2026-04-14
**Domain:** Databricks SQLAlchemy dialect integration, catalog-aware metadata, DESCRIBE EXTENDED parsing
**Confidence:** HIGH

## Summary

Phase 11 implements the DatabricksDialect class completing the third dialect in the multi-dialect architecture. The codebase is well-prepared: DatabricksConnectionConfig exists in config.py, the dialect registry already maps "databricks" to a dialect name, and connect_with_config() has an explicit NotImplementedError placeholder for this phase. The primary work is: (1) implementing DatabricksDialect as a DialectStrategy, (2) wiring it into the connection and metadata layers, (3) adding DESCRIBE TABLE EXTENDED parsing for Databricks-specific properties, and (4) adding optional catalog parameters to the three schema tools.

The databricks-sqlalchemy package (v2.0.9) provides a full SQLAlchemy dialect with Inspector support for get_schema_names, get_table_names, get_columns, get_pk_constraint, and get_foreign_keys. Critically, get_indexes returns an empty list (Databricks has no indexes). The dialect handles catalog/schema scoping natively through URL query parameters.

**Primary recommendation:** Follow the GenericDialect pattern (URL-based engine creation via connect_with_url), add DESCRIBE TABLE EXTENDED parsing as a Databricks-specific method on MetadataService, and route catalog parameters through existing tool plumbing.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use databricks-sqlalchemy + databricks-sql-connector as the Databricks driver stack. Both packages go in the `[databricks]` optional extra in pyproject.toml.
- **D-02:** DatabricksDialect.create_engine() builds a `databricks://token:{token}@{host}?http_path={path}&catalog={catalog}&schema={schema}` URL from DatabricksConnectionConfig fields. Token resolved via `resolve_env_vars()` at connection time.
- **D-03:** Missing databricks packages surface at connection time via lazy import with clear error message (same pattern as MssqlDialect with pyodbc).
- **D-04:** DatabricksDialect capability flags: supports_indexes=False, has_fast_row_counts=False, safe_procedures=frozenset().
- **D-05:** DatabricksDialect.sqlglot_dialect returns "databricks" for query validation.
- **D-06:** DatabricksDialect.quote_identifier uses backtick quoting.
- **D-07:** Extend get_table_schema response with optional Databricks-specific fields: owner, storage_format, table_type_detail, created_time, location. Populated via DESCRIBE EXTENDED.
- **D-08:** No new MCP tool -- all metadata stays in get_table_schema.
- **D-09:** Connection config sets a default catalog (defaults to "main").
- **D-10:** list_schemas, list_tables, get_table_schema gain optional catalog parameter. Databricks uses it; others ignore it.
- **D-11:** Databricks table identifiers in responses use three-level format: catalog.schema.table.
- **D-12:** Cross-catalog navigation via optional catalog parameter. Full discovery (ENRICH-02) deferred.
- **D-13:** When dialect.supports_indexes is False, indexes key is omitted entirely (not empty list).
- **D-14:** Partition columns surfaced as partition_columns list for Databricks. Omitted for non-Databricks or non-partitioned tables.

### Claude's Discretion
- **D-15:** Internal structure of DatabricksDialect class (DESCRIBE EXTENDED parsing, error handling).
- **D-16:** How MetadataService routes to DESCRIBE EXTENDED for Databricks vs Inspector.
- **D-17:** How optional catalog parameter threads through MetadataService.
- **D-18:** ConnectionManager.connect_with_config() routing for DatabricksConnectionConfig.

### Deferred Ideas (OUT OF SCOPE)
- **ENRICH-02**: Full cross-catalog schema discovery and switching
- **ENRICH-01**: Unity Catalog tag metadata (PII classification, data domain, ownership)

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAL-03 | DatabricksDialect builds databricks:// engines with token auth, catalog/schema awareness | databricks-sqlalchemy URL format verified: `databricks://token:{token}@{host}?http_path={path}&catalog={catalog}&schema={schema}`. SQLAlchemy `make_url()` parses this correctly. |
| META-01 | list_schemas, list_tables, get_table_schema work for all three dialects | databricks-sqlalchemy Inspector supports get_schema_names (SHOW SCHEMAS), get_table_names (SHOW TABLES), get_columns (cursor.columns()), get_pk_constraint, get_foreign_keys. MSSQL optimized overrides use has_fast_row_counts branching already in place. |
| META-02 | Databricks three-level namespace (catalog.schema.table) with catalog in data model | Catalog is a URL query parameter. The dialect internally uses backtick-quoted three-level references. table_id format: `{catalog}.{schema}.{table}`. |
| META-03 | Databricks table properties surfaced via DESCRIBE EXTENDED | DESCRIBE TABLE EXTENDED returns key-value rows with col_name/data_type structure. Properties available: Owner, Table Type (MANAGED/EXTERNAL), Provider (storage format), Created Time, Location. Partition columns in a separate section. |
| META-04 | get_table_schema omits index section when supports_indexes is false | MetadataService.get_table_schema currently always includes indexes when include_indexes=True. Needs gating on dialect.supports_indexes. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| databricks-sqlalchemy | 2.0.9 | SQLAlchemy dialect for Databricks SQL | Official Databricks-maintained dialect [VERIFIED: PyPI] |
| databricks-sql-connector | >=4.0.0 | DBAPI driver for Databricks SQL endpoints | Required by databricks-sqlalchemy, handles thrift/HTTP transport [VERIFIED: PyPI dependency chain] |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy | >=2.0.0 | Engine creation, Inspector API | Already a core dependency |
| sqlglot | >=30.4.2,<31.0.0 | Query validation with databricks dialect | Already in use, "databricks" dialect verified working [VERIFIED: local test] |

### Transitive Dependencies (awareness)
| Library | Version | Brought By | Note |
|---------|---------|------------|------|
| pyarrow | >=14.0.1 | databricks-sqlalchemy | Required, adds ~200MB. Already common in data stacks. |
| thrift | 0.16-0.20 | databricks-sql-connector | Thrift protocol transport |

**Installation:**
```bash
uv add --optional databricks "databricks-sqlalchemy>=2.0.0" "databricks-sql-connector>=4.0.0"
```

**Version verification:**
- databricks-sqlalchemy 2.0.9 released 2026-02-20 [VERIFIED: PyPI JSON API]
- databricks-sql-connector 4.2.5 latest [VERIFIED: PyPI JSON API]
- sqlglot "databricks" dialect: parse + transpile confirmed working [VERIFIED: local execution]

## Architecture Patterns

### Recommended Project Structure (new/modified files)
```
src/
├── db/
│   ├── dialects/
│   │   ├── __init__.py          # Add DatabricksDialect registration
│   │   └── databricks.py        # NEW: DatabricksDialect implementation
│   ├── connection.py            # Modify: connect_with_config() Databricks routing
│   └── metadata.py              # Modify: catalog param, index gating, DESCRIBE EXTENDED
├── mcp_server/
│   └── schema_tools.py          # Modify: optional catalog param on 3 tools
└── config.py                    # No changes (DatabricksConnectionConfig already exists)
```

### Pattern 1: Lazy Import with Helpful Error (from MssqlDialect)
**What:** Try importing the driver at module level, capture the error. Raise at create_engine() time with install instructions.
**When to use:** For optional-dependency dialect drivers.
**Example:**
```python
# Source: src/db/dialects/mssql.py lines 13-20
try:
    import databricks.sql  # noqa: F401
    _databricks_import_error = None
except ImportError as e:
    _databricks_import_error = e

# In create_engine():
if _databricks_import_error is not None:
    raise ImportError(
        "Databricks support requires databricks-sqlalchemy. "
        "Install with: pip install dbmcp[databricks]"
    ) from _databricks_import_error
```
[VERIFIED: existing MssqlDialect pattern in codebase]

### Pattern 2: URL Construction from Config Fields
**What:** Build the databricks:// URL from DatabricksConnectionConfig fields, then pass to SQLAlchemy create_engine.
**When to use:** In DatabricksDialect.create_engine().
**Example:**
```python
# Source: Databricks docs + codebase pattern
def create_engine(self, **kwargs) -> Engine:
    host = kwargs["host"]
    http_path = kwargs["http_path"]
    token = kwargs["token"]
    catalog = kwargs.get("catalog", "main")
    schema = kwargs.get("schema", "default")
    
    url = (
        f"databricks://token:{token}@{host}"
        f"?http_path={http_path}&catalog={catalog}&schema={schema}"
    )
    return sa_create_engine(url, pool_pre_ping=True, echo=False)
```
[VERIFIED: URL format from Databricks official docs]

### Pattern 3: Dialect-Gated Metadata in MetadataService
**What:** Use self._dialect to conditionally add Databricks-specific metadata to get_table_schema responses.
**When to use:** When extending get_table_schema with DESCRIBE EXTENDED properties.
**Example:**
```python
# In MetadataService.get_table_schema():
if self._dialect and self._dialect.name == "databricks" and include_indexes:
    # No indexes for Databricks
    pass
elif include_indexes:
    result["indexes"] = [...]

# Better: Use capability flag
if include_indexes and (not self._dialect or self._dialect.supports_indexes):
    result["indexes"] = [...]
```
[VERIFIED: existing has_fast_row_counts branching pattern in metadata.py]

### Pattern 4: DESCRIBE TABLE EXTENDED Parsing
**What:** Execute `DESCRIBE TABLE EXTENDED {catalog}.{schema}.{table}` and parse the key-value rows.
**When to use:** To extract owner, storage_format, table_type_detail, created_time, location, partition_columns.
**DTE Output Format:**
```
col_name          | data_type
------------------|-----------
id                | bigint
name              | string
                  |                    <-- blank separator
# Partition Information |
# col_name        | data_type
dt                | date
                  |                    <-- blank separator  
# Detailed Table Information |
Database          | my_schema
Table             | my_table
Owner             | user@domain.com
Created Time      | Wed Jan 15 10:30:00 UTC 2025
Type              | MANAGED
Provider          | delta
Location          | dbfs:/user/hive/warehouse/my_table
...
```
[CITED: docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-describe-table.html]

### Pattern 5: connect_with_config Routing
**What:** In ConnectionManager.connect_with_config(), build the URL from DatabricksConnectionConfig and delegate to connect_with_url().
**When to use:** Replace the NotImplementedError at line 418.
**Example:**
```python
elif isinstance(config, DatabricksConnectionConfig):
    token = resolve_env_vars(config.token) if config.token else ""
    url = (
        f"databricks://token:{token}@{config.host}"
        f"?http_path={config.http_path}"
        f"&catalog={config.catalog}"
        f"&schema={config.schema_name}"
    )
    return self.connect_with_url(url, dialect, query_timeout)
```
[VERIFIED: existing GenericConnectionConfig pattern in connection.py line 414-416]

### Anti-Patterns to Avoid
- **Importing databricks at module top level unconditionally:** Breaks servers without databricks installed. Use lazy import pattern.
- **Catching only SQLAlchemyError around Databricks Inspector calls:** The connector raises DB-API exceptions (databricks.sql.exc.Error hierarchy) that may not be wrapped by SQLAlchemy in all code paths. Catch both.
- **Using DESCRIBE TABLE EXTENDED AS JSON:** Requires Databricks Runtime 16.2+ (very recent). Stick to text parsing for broad compatibility.
- **Storing catalog in the dialect class:** Catalog belongs on the connection config and is passed through tool parameters. The dialect should be stateless regarding catalog.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Databricks SQL execution | Custom HTTP client | databricks-sql-connector | Handles thrift protocol, retries, auth token refresh |
| Schema/table introspection | Custom SHOW queries | SQLAlchemy Inspector via databricks-sqlalchemy | Already implements get_schema_names, get_table_names, get_columns |
| URL construction | String concatenation | urllib.parse.urlencode for query params | Handles special characters in tokens, paths |
| PK/FK constraint parsing | Custom DTE parser | databricks-sqlalchemy._parse | Already parses PK/FK from DTE output |

**Key insight:** databricks-sqlalchemy already handles the hard parts (cursor management, type mapping, basic Inspector methods). Our DatabricksDialect is a thin wrapper that constructs the URL and adds capability flags. The main custom work is parsing DESCRIBE EXTENDED for table properties (owner, storage format, etc.) which databricks-sqlalchemy doesn't expose through Inspector.

## Common Pitfalls

### Pitfall 1: Non-SQLAlchemy Exceptions from Databricks Connector
**What goes wrong:** Code catches SQLAlchemyError but Databricks connector raises databricks.sql.exc.OperationalError (DB-API exception, not SQLAlchemy) for network/auth failures.
**Why it happens:** SQLAlchemy wraps most DBAPI exceptions in DBAPIError, but edge cases (especially during Inspector reflection) can leak raw exceptions.
**How to avoid:** In MetadataService methods that execute raw SQL (DESCRIBE EXTENDED), catch both SQLAlchemyError and Exception with appropriate logging. In the MCP tool layer, the existing broad except clause in schema_tools.py already handles this.
**Warning signs:** Unhandled exception tracebacks showing `databricks.sql.exc.*` types.
[VERIFIED: databricks-sqlalchemy source code analysis, databricks-sql-python exc.py hierarchy]

### Pitfall 2: Token URL-Encoding Issues
**What goes wrong:** Databricks personal access tokens contain characters that need URL-encoding when embedded in the connection URL.
**Why it happens:** Tokens are placed in the password position of the URL: `databricks://token:{token}@host`.
**How to avoid:** Use `urllib.parse.quote_plus()` for the token value when constructing the URL, or use `sqlalchemy.engine.url.URL.create()` which handles encoding.
**Warning signs:** Connection failures with "invalid token" messages despite correct token value.
[ASSUMED]

### Pitfall 3: Catalog Parameter Ignored by Inspector
**What goes wrong:** Passing a catalog parameter to Inspector.get_table_names(schema=...) doesn't switch catalogs. The catalog is set at engine-creation time via the URL.
**Why it happens:** SQLAlchemy Inspector doesn't have a catalog concept in its API. Databricks-sqlalchemy sets catalog when the connection is created.
**How to avoid:** For cross-catalog queries, execute raw SQL (`SHOW TABLES IN {catalog}.{schema}`) rather than using Inspector. For the default catalog, rely on the engine's configured catalog.
**Warning signs:** get_table_names returning tables from the wrong catalog.
[VERIFIED: databricks-sqlalchemy source -- catalog set in create_connect_args, not per-Inspector-call]

### Pitfall 4: DESCRIBE EXTENDED Output Parsing Fragility
**What goes wrong:** The text format of DESCRIBE TABLE EXTENDED output changes between Databricks Runtime versions.
**Why it happens:** Databricks docs explicitly state: "the non-JSON report format is subject to change."
**How to avoid:** Parse defensively -- use key matching (e.g., find "Owner" in col_name) rather than positional parsing. Return None for missing properties rather than raising.
**Warning signs:** KeyError or IndexError in DTE parsing code after Databricks Runtime upgrades.
[CITED: docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-describe-table.html]

### Pitfall 5: pyarrow Dependency Size
**What goes wrong:** Installing databricks-sqlalchemy pulls in pyarrow (~200MB), surprising users who expect a lightweight install.
**Why it happens:** pyarrow>=14.0.1 is a hard dependency of databricks-sqlalchemy.
**How to avoid:** Document this in install instructions. The optional extras pattern ([databricks]) already isolates this.
**Warning signs:** Slow CI/CD pipelines, large Docker images.
[VERIFIED: PyPI dependency chain]

## Code Examples

### DESCRIBE TABLE EXTENDED Parsing for Table Properties
```python
# Source: Databricks DTE output format (docs.databricks.com)
def _parse_databricks_table_properties(
    self, table_name: str, schema_name: str, catalog: str
) -> dict:
    """Parse DESCRIBE TABLE EXTENDED for Databricks-specific properties.
    
    Returns dict with optional keys: owner, storage_format, table_type_detail,
    created_time, location, partition_columns.
    """
    qualified = f"`{catalog}`.`{schema_name}`.`{table_name}`"
    
    with self.engine.connect() as conn:
        result = conn.execute(text(f"DESCRIBE TABLE EXTENDED {qualified}"))
        rows = result.fetchall()
    
    props = {}
    partition_cols = []
    in_partition_section = False
    in_detail_section = False
    
    for row in rows:
        col_name = (row[0] or "").strip()
        data_type = (row[1] or "").strip()
        
        # Section markers
        if col_name.startswith("# Partition Information"):
            in_partition_section = True
            in_detail_section = False
            continue
        elif col_name.startswith("# Detailed Table Information"):
            in_partition_section = False
            in_detail_section = True
            continue
        elif col_name.startswith("#"):
            continue  # Skip header rows
        elif not col_name and not data_type:
            in_partition_section = False
            # Don't reset detail section -- it continues to end
            continue
        
        if in_partition_section and col_name and not col_name.startswith("#"):
            partition_cols.append(col_name)
        
        if in_detail_section:
            key_map = {
                "Owner": "owner",
                "Provider": "storage_format",
                "Type": "table_type_detail",
                "Created Time": "created_time",
                "Location": "location",
            }
            if col_name in key_map:
                props[key_map[col_name]] = data_type
    
    if partition_cols:
        props["partition_columns"] = partition_cols
    
    return props
```

### DatabricksDialect Skeleton
```python
# Source: based on MssqlDialect + GenericDialect patterns in codebase
class DatabricksDialect:
    """Databricks dialect implementation."""

    @property
    def name(self) -> str:
        return "databricks"

    @property
    def sqlglot_dialect(self) -> str:
        return "databricks"

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def has_fast_row_counts(self) -> bool:
        return False

    @property
    def safe_procedures(self) -> frozenset[str]:
        return frozenset()

    def quote_identifier(self, identifier: str) -> str:
        return f"`{identifier}`"

    def create_engine(self, **kwargs) -> Engine:
        if _databricks_import_error is not None:
            raise ImportError(
                "Databricks support requires databricks-sqlalchemy. "
                "Install with: pip install dbmcp[databricks]"
            ) from _databricks_import_error
        # Build URL from kwargs, return sa_create_engine(url)
        ...

    def fast_row_counts(self, engine, schema_name=None) -> dict[str, int]:
        return {}
```

### Index Gating in MetadataService.get_table_schema
```python
# Before (current):
if include_indexes:
    indexes = self.get_indexes(table_name, schema_name)
    result["indexes"] = [...]

# After:
if include_indexes and (not self._dialect or self._dialect.supports_indexes):
    indexes = self.get_indexes(table_name, schema_name)
    result["indexes"] = [...]
# When supports_indexes is False, "indexes" key is absent entirely (D-13)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Text-based DTE parsing | DESCRIBE TABLE EXTENDED AS JSON | DBR 16.2 (late 2025) | Structured output, but too new for broad adoption |
| databricks-sqlalchemy v1 (thrift only) | databricks-sqlalchemy v2 | 2024 | Cleaner Inspector support, better type mapping |
| Single-catalog Databricks | Unity Catalog (multi-catalog) | 2022+ | Three-level namespace is standard now |

**Deprecated/outdated:**
- DTE text format: Databricks warns it's "subject to change" but it's still the only universally-available option. JSON format (DBR 16.2+) is the future but not yet broadly deployable.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Token values may need URL-encoding when embedded in databricks:// URLs | Pitfall 2 | Connection failures for tokens with special chars; fix is trivial (add quote_plus) |
| A2 | DESCRIBE TABLE EXTENDED text output uses consistent section headers ("# Partition Information", "# Detailed Table Information") across DBR versions | Code Examples | Parsing breaks on some DBR versions; mitigated by defensive parsing |
| A3 | Inspector.get_table_names respects the catalog set at engine creation time (not overridable per-call) | Pitfall 3 | Cross-catalog list_tables/list_schemas would silently use wrong catalog |

## Open Questions

1. **Cross-catalog Inspector behavior**
   - What we know: Catalog is set in URL at engine creation. Inspector methods use that catalog.
   - What's unclear: Can we use raw SQL (`USE CATALOG x; SHOW TABLES`) to switch catalogs within a connection, or must we create a new engine?
   - Recommendation: For D-10 (optional catalog param), use raw SQL execution (`SHOW SCHEMAS IN {catalog}`, `SHOW TABLES IN {catalog}.{schema}`) when the requested catalog differs from the connection default. This avoids creating new engines.

2. **pyarrow dependency size impact**
   - What we know: pyarrow >=14.0.1 is mandatory via databricks-sqlalchemy.
   - What's unclear: Whether this affects CI/CD significantly for this project.
   - Recommendation: Accept the dependency; document in pyproject.toml comment. This is standard for Databricks tooling.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| databricks-sqlalchemy | DatabricksDialect | Not installed | -- | Install via `[databricks]` extra |
| databricks-sql-connector | databricks-sqlalchemy | Not installed | -- | Transitive dep of above |
| pyarrow | databricks-sqlalchemy | Not installed | -- | Transitive dep of above |
| sqlglot (databricks dialect) | Query validation | Installed | 30.4.2 | -- (already works) |

**Missing dependencies with no fallback:**
- databricks-sqlalchemy + databricks-sql-connector: Must be installed for Databricks support. This is expected -- they go in the optional `[databricks]` extra per D-01.

**Missing dependencies with fallback:**
- None. All dependencies are either already available or correctly gated behind optional extras.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 0.21.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x --tb=short` |
| Full suite command | `uv run pytest tests/ -x --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAL-03 | DatabricksDialect protocol compliance + create_engine | unit | `uv run pytest tests/unit/test_databricks_dialect.py -x` | Wave 0 |
| DIAL-03 | Lazy import error handling | unit | `uv run pytest tests/unit/test_databricks_dialect.py::TestDatabricksLazyImport -x` | Wave 0 |
| META-01 | list_schemas/list_tables/get_table_schema work for all 3 dialects | unit | `uv run pytest tests/unit/test_metadata.py -x` | Exists (extend) |
| META-02 | Three-level namespace in responses | unit | `uv run pytest tests/unit/test_databricks_dialect.py::TestCatalogNamespace -x` | Wave 0 |
| META-03 | DESCRIBE EXTENDED properties parsed | unit | `uv run pytest tests/unit/test_databricks_dialect.py::TestDescribeExtended -x` | Wave 0 |
| META-04 | Index section omitted when supports_indexes=False | unit | `uv run pytest tests/unit/test_metadata.py::TestIndexGating -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x --tb=short`
- **Per wave merge:** `uv run pytest tests/ -x --tb=short`
- **Phase gate:** Full suite green + `uv run ruff check src/` clean

### Wave 0 Gaps
- [ ] `tests/unit/test_databricks_dialect.py` -- covers DIAL-03, META-02, META-03 (protocol compliance, URL construction, DTE parsing, catalog namespace)
- [ ] Extend `tests/unit/test_metadata.py` -- covers META-04 (index gating when supports_indexes=False)
- [ ] Extend `tests/unit/test_connect_tool.py` -- covers DatabricksConnectionConfig routing in connect_with_config
- [ ] No framework install needed -- pytest infrastructure is solid (800 tests collected)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Token resolved via resolve_env_vars() at connection time; never logged or stored in Connection model |
| V3 Session Management | no | -- |
| V4 Access Control | no | Read-only model enforced by query validation layer (unchanged) |
| V5 Input Validation | yes | Catalog/schema/table names in DESCRIBE queries must use backtick quoting to prevent injection |
| V6 Cryptography | no | -- |

### Known Threat Patterns for Databricks Dialect

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token leakage in logs | Information Disclosure | Token never logged; Connection model excludes credentials (NFR-005) |
| SQL injection via catalog/schema params | Tampering | Backtick-quote all identifiers in DESCRIBE queries; use parameterized queries where possible |
| Token in URL visible via engine.url | Information Disclosure | SQLAlchemy's render_as_string(hide_password=True) used in error messages |

## Sources

### Primary (HIGH confidence)
- PyPI JSON API for databricks-sqlalchemy 2.0.9 -- version, dependencies confirmed
- PyPI JSON API for databricks-sql-connector 4.2.5 -- version, dependencies confirmed
- GitHub databricks/databricks-sqlalchemy base.py -- Inspector methods, URL format, exception handling
- GitHub databricks/databricks-sqlalchemy _parse.py -- DTE output parsing structure
- GitHub databricks/databricks-sql-python exc.py -- Exception hierarchy
- Databricks docs (docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-describe-table.html) -- DTE output format, AS JSON availability
- Databricks docs (docs.databricks.com/en/dev-tools/sqlalchemy.html) -- URL format confirmation
- Local codebase verification -- all existing code patterns, sqlglot dialect support

### Secondary (MEDIUM confidence)
- Databricks docs on DESCRIBE TABLE EXTENDED output section headers -- verified against docs but parsing of specific property keys (Owner, Provider, Type, etc.) based on documented output format

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions verified against PyPI, dialect tested locally
- Architecture: HIGH - follows established codebase patterns (MssqlDialect, GenericDialect), all integration points identified in existing code
- Pitfalls: HIGH - exception hierarchy verified from source, DTE format confirmed from official docs
- DESCRIBE EXTENDED parsing: MEDIUM - output format documented but "subject to change" per Databricks

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable -- databricks-sqlalchemy release cadence is monthly)
