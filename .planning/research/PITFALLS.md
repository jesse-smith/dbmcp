# Domain Pitfalls

**Domain:** Multi-dialect database support (dbmcp v2.0 -- adding Databricks and generic SQLAlchemy dialects to existing SQL Server MCP server)
**Researched:** 2026-04-13
**Confidence:** HIGH for MSSQL-specific integration risks (direct codebase evidence), MEDIUM for Databricks-specific issues (vendor docs + GitHub issues), LOW for some sqlglot transpilation edge cases (limited cross-dialect testing evidence)

## Critical Pitfalls

### Pitfall 1: SQLAlchemy Inspector Returns Different Shapes Per Dialect

**What goes wrong:** The existing MetadataService uses SQLAlchemy Inspector for `get_columns`, `get_pk_constraint`, `get_foreign_keys`, and `get_indexes`. These methods return dict structures whose keys and value types vary by dialect in undocumented ways. Specific known differences:

- **`get_pk_constraint`**: Databricks with Hive metastore returns an empty dict (no PK concept). Unity Catalog returns informational-only constraints that may or may not populate `constrained_columns`. SQL Server always returns actual enforced PKs.
- **`get_indexes`**: Databricks does not have traditional indexes. The Inspector returns an empty list, but may also raise `NotImplementedError` depending on the databricks-sqlalchemy version. The current `get_indexes` method in `metadata.py:561` will silently return `[]` due to the `except SQLAlchemyError` handler -- but `NotImplementedError` is NOT a `SQLAlchemyError`. It would propagate unhandled.
- **`get_foreign_keys`**: Databricks Unity Catalog supports informational FK constraints (not enforced). Hive metastore does not support them at all. The Inspector may return empty or raise.
- **`get_columns` type strings**: SQL Server returns types like `INTEGER`, `NVARCHAR(255)`, `DATETIME2`. Databricks returns `INT`, `STRING`, `TIMESTAMP`, `TIMESTAMP_NTZ`. The `str(col["type"])` call in `metadata.py:539` produces different strings for semantically equivalent types.
- **`autoincrement` field**: Databricks supports `Identity()` columns on BigInteger only. The `col.get("autoincrement", False)` in `metadata.py:550` may return unexpected values or be absent entirely.

**Why it happens:** SQLAlchemy's Inspector is an abstraction over dialect-specific implementations. The documentation explicitly says "consult dialect-specific sections for detailed behavioral differences." Each dialect author implements what makes sense for their database, and the return shapes are loosely specified.

**Consequences:** Silent data corruption in metadata responses. Users see `has_primary_key: false` for Databricks tables that DO have informational PKs. `get_table_schema` returns empty `indexes` and `foreign_keys` arrays even when Databricks metadata exists. Worse: `NotImplementedError` propagates through the MCP tool layer as "Unexpected error" instead of a clean "not supported" message.

**Prevention:**
1. The DialectStrategy protocol MUST define which Inspector methods are available per dialect. `DatabricksDialect.supports_indexes` returns False, and the MetadataService skips the call entirely instead of calling and handling the error.
2. Wrap every Inspector call in the dialect strategy, not in try/except at the MetadataService level. The strategy knows what its dialect supports; the service should not guess.
3. Add `NotImplementedError` to the exception handlers in `get_indexes` and `get_foreign_keys` NOW, even before the dialect work. It is a latent bug.
4. Normalize type strings through a mapping layer in the dialect strategy. `STRING` -> `VARCHAR`, `TIMESTAMP_NTZ` -> `DATETIME2` for display consistency, or accept that type strings are dialect-specific and document this in tool responses.

**Detection:** Test that exercises `get_table_schema` on a Databricks connection and checks that all fields are populated or explicitly marked as unsupported.

**Phase:** Dialect strategy protocol definition (early). The protocol MUST encode capability flags before any metadata code changes.

---

### Pitfall 2: Three-Level Namespace (Catalog.Schema.Table) vs Two-Level (Schema.Table)

**What goes wrong:** The entire codebase assumes a two-level namespace: `schema_name.table_name`. This is hardcoded in:
- `metadata.py`: `table_id = f"{schema_name}.{table_name}"` (line 524)
- `column_stats.py`: `self._qualified_table = f"[{schema_name}].[{table_name}]"` (line 82)
- `fk_candidates.py`: `source_table = f"[{self.source_schema}].[{self.source_table}]"` (line 264)
- `pk_discovery.py`: `self._qualified_table = f"[{schema_name}].[{table_name}]"` (line 39)
- All MCP tool responses embed `schema_name` as a top-level concept with no `catalog_name` field.

Databricks Unity Catalog uses three levels: `catalog.schema.table`. When a user connects to a Databricks workspace, `Inspector.get_schema_names()` returns schemas within the CURRENT catalog only. To see schemas in other catalogs, you must switch catalogs or use three-part names. The `list_schemas` tool will show only the default catalog's schemas with no way to discover or switch catalogs.

**Why it happens:** SQL Server's `USE database` sets the database context, and schemas are within that database. This maps cleanly to "connect to a database, see its schemas." Databricks' `USE CATALOG` sets the catalog context, and schemas are within that catalog. But there is no equivalent of "connecting to a catalog" in the connection URL -- the catalog is set after connection via SQL or connection properties. The SQLAlchemy connection URL for Databricks includes `catalog=` and `schema=` parameters, but Inspector still operates within the current catalog.

**Consequences:** Users connecting to a Databricks workspace with multiple catalogs see only one catalog's schemas. The `schema_name` parameter in every MCP tool becomes ambiguous -- does `"analytics"` mean `catalog_x.analytics` or `catalog_y.analytics`? Table IDs like `analytics.customers` collide across catalogs.

**Prevention:**
1. Add an optional `catalog` field to the connection config and table identifier model. For MSSQL, catalog maps to database name (already handled by the connection). For Databricks, catalog is explicit.
2. The DialectStrategy must expose `supports_catalogs: bool` and `list_catalogs()`. When true, `list_schemas` should accept an optional `catalog` parameter.
3. Qualified table names in Databricks should be `catalog.schema.table` in generated SQL. The quoting strategy changes too: Databricks uses backticks, not brackets.
4. Do NOT try to make the MCP tool interface catalog-aware in v2.0. Instead, have the Databricks connection config specify a default catalog, and make it clear in tool responses which catalog is active. Full catalog navigation is a future feature.

**Detection:** User connects to Databricks, calls `list_schemas`, sees only `default` catalog schemas. Tries to query a table in another catalog and gets "table not found."

**Phase:** Connection config redesign (early) and dialect strategy definition. The catalog concept must be in the data model even if the MCP tools don't fully expose it yet.

---

### Pitfall 3: Hardcoded SQL Server Syntax in Analysis Modules

**What goes wrong:** The analysis modules (`column_stats.py`, `fk_candidates.py`, `pk_discovery.py`) contain SQL that is syntactically valid ONLY for SQL Server:

- **`[bracket]` quoting**: `f"[{column_name}]"` everywhere. Databricks uses backticks. PostgreSQL uses double quotes. Running `[column_name]` against Databricks produces a syntax error.
- **`INFORMATION_SCHEMA` queries**: Used in `column_stats.py:93`, `fk_candidates.py:65-99`, `pk_discovery.py:58-74`. Databricks does not support `INFORMATION_SCHEMA`. It uses `SHOW COLUMNS`, `DESCRIBE TABLE`, or `system.information_schema` (Unity Catalog only, different structure).
- **`sys.indexes`** join in `fk_candidates.py:216-227`: Pure SQL Server DMV. No equivalent in Databricks or generic databases.
- **`STRING_SPLIT`** in `fk_candidates.py:69`: SQL Server-specific function. Not available in Databricks (use `split()` or `explode()`).
- **`SELECT TOP N`** in `column_stats.py:321`: SQL Server syntax. Databricks and ANSI SQL use `LIMIT N`.
- **`DATEDIFF(day, ...)` and `CAST(... AS TIME)`** in `column_stats.py:256-265`: SQL Server datetime functions. Databricks has `datediff()` but with different argument order (`datediff(col1, col2)` returns days, vs SQL Server's `DATEDIFF(datepart, start, end)`).
- **`LEN()`** in `column_stats.py:306`: SQL Server function. Databricks uses `LENGTH()` or `LEN()` (supported as alias, but not guaranteed across all dialects).
- **`STDEV()`** in `column_stats.py:218`: SQL Server aggregate. Databricks uses `STDDEV()`.
- **`CAST(... AS FLOAT)`** in `column_stats.py:215`: Works on both, but Databricks prefers `DOUBLE` over `FLOAT`.

This is not just a "search and replace" problem. The SQL is constructed via f-strings with embedded column names and table references. Each query needs to be rewritten per dialect or transpiled.

**Why it happens:** The analysis modules were built for SQL Server only. There was no abstraction layer because there was only one dialect. The queries use SQL Server idioms because that is what the developer knew.

**Consequences:** Every analysis tool (`get_column_info`, `find_pk_candidates`, `find_fk_candidates`) throws SQL syntax errors on Databricks. These are 3 of 9 MCP tools -- a third of the tool surface is broken on non-MSSQL databases.

**Prevention:**
1. This is where the three-tier query strategy pays off. Tier 1 (Inspector) handles basic metadata. Tier 2 (standard SQL) handles analysis queries using ANSI-compatible SQL transpiled via sqlglot. Tier 3 (dialect-specific) handles optimized queries like DMV-based row counts.
2. For the analysis modules, define the INTENT as a Python function, then generate dialect-appropriate SQL. Example: "get distinct count and null count for column X in table Y" is the intent; the SQL differs by dialect.
3. Use sqlglot's `transpile()` to convert a canonical ANSI SQL template to the target dialect. This handles `TOP` vs `LIMIT`, identifier quoting, and function name differences.
4. Do NOT try to make every analysis query work on every dialect in v2.0. Define a capability matrix: which analysis features are available per dialect. PK discovery via constraints is MSSQL+Databricks (Unity Catalog only). FK candidate search with overlap is MSSQL-only initially. Column stats basic (distinct/null) is universal. Column stats datetime is dialect-specific.

**Detection:** Run any analysis tool against a non-MSSQL database. It will fail immediately with a SQL syntax error.

**Phase:** Analysis module refactoring (later phase, after dialect strategy and metadata are working). This is the highest-effort change in the entire milestone.

---

### Pitfall 4: sqlglot Dialect Mismatch Between Validation and Execution

**What goes wrong:** The validation module (`validation.py:107`) hardcodes `dialect="tsql"` in `sqlglot.parse()`. When a user submits a Databricks SQL query for execution, it is validated by parsing as T-SQL. Databricks SQL uses different syntax that sqlglot's TSQL parser may reject or misparse:

- **Backtick identifiers**: `` `table`.`column` `` is valid Databricks SQL but may confuse the TSQL parser.
- **Colon JSON extraction**: `column:path` is Databricks syntax for JSON field access. TSQL parser sees this as a parameter placeholder or syntax error.
- **`LATERAL VIEW`**: Databricks/Spark SQL syntax for table-generating functions. No TSQL equivalent.
- **`QUALIFY`**: Databricks supports `QUALIFY` clause (window function filter). TSQL does not have this.
- **`PIVOT`/`UNPIVOT`**: Both dialects support these but with different syntax.
- **Lambda expressions**: Databricks supports `TRANSFORM(array, x -> x + 1)`. TSQL has no lambda syntax.

A valid Databricks query parsed as TSQL may: (a) fail to parse entirely (reported as `PARSE_FAILURE` = query rejected), (b) parse to a different AST than intended (e.g., a SELECT that looks like a Command), or (c) parse correctly by coincidence but with wrong semantics.

**Why it happens:** The validation module was written for a single-dialect system. The `dialect="tsql"` parameter was correct when SQL Server was the only target.

**Consequences:** Users cannot execute valid Databricks SQL through the MCP server. The validation rejects queries that would run fine on Databricks. This is a blocker for basic usability on non-MSSQL databases.

**Prevention:**
1. `validate_query` MUST accept a `dialect` parameter and pass it to `sqlglot.parse()`. This is a signature change but backward-compatible if defaulted to `"tsql"`.
2. The dialect parameter should come from the connection's dialect strategy, not from the user. When a user calls `execute_query` with a `connection_id`, the system looks up the dialect for that connection and passes it to validation.
3. sqlglot's `"databricks"` dialect exists and handles Databricks-specific syntax. Use it.
4. The DENIED_TYPES map (`exp.Insert`, `exp.Delete`, etc.) is dialect-agnostic -- these AST node types are the same regardless of parse dialect. The denylist logic should work without changes.
5. The SAFE_PROCEDURES list is SQL Server-specific. For Databricks, stored procedures are not a concept (they have UDFs). The Execute/Command checking logic should be skipped for non-MSSQL dialects.
6. Test with actual Databricks SQL patterns: `SELECT * FROM catalog.schema.table`, `SELECT col:nested_field FROM ...`, `SELECT * FROM table QUALIFY row_number() OVER (...) = 1`.

**Detection:** User executes a valid Databricks query and gets "Parse failure" or "Unrecognized statement" from validation.

**Phase:** Early -- this is a prerequisite for any query execution on non-MSSQL databases. Can be done as a standalone change before the full dialect strategy.

---

### Pitfall 5: Breaking connect_database Interface Without Migration Path

**What goes wrong:** The current `connect_database` tool has 10 SQL Server-specific parameters (server, database, port, authentication_method, trust_server_cert, connection_timeout, tenant_id, username, password, connection_name). The v2.0 plan simplifies this to `connection_name` / `sqlalchemy_url`. This is a BREAKING CHANGE for every existing MCP client configuration.

MCP tool interfaces are consumed by LLM agents via tool schemas. When the tool schema changes, the LLM's learned patterns for calling the tool break. Unlike a REST API where you can version endpoints, MCP tools are identified by name only. Changing the parameter set of `connect_database` means:

1. Every existing TOML config with `[connections.xxx]` sections using `server`/`database` fields needs updating.
2. Every Claude/LLM conversation history that references the old parameters becomes misleading if the user asks "connect like last time."
3. Cursor/VS Code MCP client configurations that call `connect_database` with explicit params stop working.

**Why it happens:** The original interface was designed for SQL Server's connection model (server + database + auth method). A generic interface needs a different shape. The temptation is to rip off the bandaid and ship the clean interface.

**Consequences:** Every existing user's configuration breaks on upgrade. No migration path means they must manually rewrite configs. If the new interface is the ONLY option, users who only use SQL Server pay a complexity cost (learning sqlalchemy_url syntax) for multi-dialect support they may not need.

**Prevention:**
1. Support BOTH interfaces during v2.0. The old SQL Server-specific parameters continue to work and internally construct a `mssql+pyodbc://` URL. The new `sqlalchemy_url` parameter is an alternative for power users and non-MSSQL databases.
2. The `connection_name` parameter ALREADY exists and is the preferred path. Evolve the TOML config to support a `dialect` field that determines which connection parameters are expected. Existing configs without `dialect` default to `dialect = "mssql"` and work unchanged.
3. Deprecation warnings: when old-style parameters are used directly (not via `connection_name`), log a deprecation notice suggesting migration to named connections.
4. Document the migration path explicitly: "If you were calling `connect_database(server='x', database='y', ...)`, use `connect_database(connection_name='myconn')` with a TOML config instead."

**Detection:** Existing user upgrades dbmcp and gets "unexpected parameter 'server'" or similar from their MCP client.

**Phase:** Connection config redesign (early). This must be designed before implementation starts because it affects every downstream tool.

---

## Moderate Pitfalls

### Pitfall 6: databricks-sqlalchemy Inspector Raises Non-SQLAlchemy Exceptions

**What goes wrong:** The databricks-sqlalchemy library (v2.0.9) has known issues with cross-catalog queries, UUID handling, and missing type support (INTERVAL, VARIANT, JSON types). When Inspector methods encounter unsupported types or catalog boundaries, they may raise `TypeError`, `ValueError`, `NotImplementedError`, or even `AttributeError` -- none of which inherit from `SQLAlchemyError`.

The current MetadataService catches only `SQLAlchemyError` in its generic paths (e.g., `metadata.py:131`, `metadata.py:146`, `metadata.py:288`, `metadata.py:373`). Non-SQLAlchemy exceptions propagate to the MCP tool layer, where they hit the generic `except Exception` handler and produce unhelpful "Unexpected error" messages.

**Why it happens:** databricks-sqlalchemy is a third-party dialect with 50+ open issues. Its Inspector implementation is less mature than the core SQLAlchemy MSSQL dialect. Error handling in the dialect itself is inconsistent.

**Prevention:**
1. Add `(SQLAlchemyError, NotImplementedError, TypeError)` to catch clauses in metadata generic paths. This is defensive but necessary for third-party dialects.
2. Better: the DialectStrategy wraps Inspector calls and normalizes exceptions to a consistent set (e.g., `DialectError`, `UnsupportedFeatureError`).
3. Pin `databricks-sqlalchemy` to a tested version and add it to the same "explicit validation before merge" policy that sqlglot already has.

**Detection:** Connect to Databricks and call `get_table_schema` on a table with VARIANT or MAP columns. The MCP tool returns "Unexpected error: TypeError" instead of useful metadata.

**Phase:** Dialect strategy implementation. The strategy layer is the right place to normalize exceptions.

---

### Pitfall 7: Databricks Connection Lifecycle Differs Fundamentally

**What goes wrong:** The current ConnectionManager is built around pyodbc's connection model: open a socket, authenticate, keep alive in pool, recycle when stale. Databricks connections work differently:

- **Warehouse vs Cluster**: Databricks SQL Warehouses auto-suspend after inactivity (default: 10 minutes). When a query arrives after suspension, the warehouse takes 30-120 seconds to start. The connection appears "alive" (HTTP session exists) but queries timeout waiting for compute.
- **Rate limiting**: Databricks API has rate limits (varies by plan). Rapid metadata introspection (calling Inspector methods in a loop for many tables) can hit rate limits and return HTTP 429 errors, which databricks-sql-connector surfaces as `OperationalError`.
- **Connection creation overhead**: SQL Server connections via pyodbc are cheap (~50ms). Databricks connections go through HTTPS/Thrift and take 1-5 seconds. Pool warming is expensive.
- **Token authentication**: Databricks uses personal access tokens or OAuth M2M tokens. These are not ODBC connection strings -- they go in HTTP headers. The current `_build_odbc_connection_string` method is irrelevant.

**Why it happens:** The ConnectionManager was designed for SQL Server's connection semantics. Databricks is an HTTP-based cloud service with fundamentally different performance characteristics and failure modes.

**Consequences:** Users experience 30-120 second hangs on first query after idle period (warehouse cold start). Rapid `list_tables` + `get_table_schema` calls hit rate limits. Connection pool configuration (pool_size, max_overflow) is meaningless for HTTP-based connections.

**Prevention:**
1. Databricks engine creation must bypass the ODBC path entirely. Use `create_engine("databricks://", ...)` with the databricks-sqlalchemy dialect, not `mssql+pyodbc://`.
2. The DialectStrategy should own engine creation. `MssqlDialect.create_engine()` builds the ODBC URL. `DatabricksDialect.create_engine()` builds the Databricks URL with token auth.
3. Add warehouse cold-start awareness: configure longer connection timeouts for Databricks (60s+), and document that first-query latency is expected.
4. Add rate-limit retry logic in the Databricks dialect strategy: catch HTTP 429 and retry with exponential backoff. Do NOT add this in the generic ConnectionManager.
5. Pool configuration for Databricks should use smaller pools (pool_size=2) since connections are expensive and the server-side is stateless.

**Detection:** Connect to a Databricks SQL Warehouse that has auto-suspended. First query hangs for 60+ seconds or times out.

**Phase:** Connection config redesign and dialect strategy implementation. Engine creation is the first thing that must be dialect-aware.

---

### Pitfall 8: Test Suite Assumes SQL Server Everywhere

**What goes wrong:** 682+ tests assume SQL Server. Specific patterns that break for multi-dialect:

- **SQLite as "generic" stand-in**: The test suite uses SQLite for unit tests and SQL Server for integration. SQLite is NOT representative of Databricks behavior. SQLite has no schemas, no catalogs, no stored procedures, no type enforcement. Tests passing on SQLite give false confidence for Databricks support.
- **Hardcoded SQL in test fixtures**: Test helpers that create tables use SQL Server DDL syntax (`CREATE TABLE [dbo].[TestTable]`). These fixtures cannot be reused for Databricks tests.
- **Mock-based tests for Inspector**: If tests mock Inspector methods, the mocks encode SQL Server's return shapes. Databricks returns different shapes (see Pitfall 1). The mocks pass but real connections fail.
- **Error message assertions**: ~30+ tests assert on specific error message strings that mention SQL Server concepts ("EXEC", "stored procedure", "DMV"). These assertions are correct for SQL Server but meaningless for Databricks.
- **Connection test probes**: `_test_connection` executes `SELECT @@VERSION AS version, DB_NAME() AS database_name`. Both `@@VERSION` and `DB_NAME()` are SQL Server-specific. Databricks would error on these.

**Why it happens:** The test suite was built for a single-dialect system. Test-first development means the tests encode the current system's assumptions.

**Consequences:** No meaningful test coverage for Databricks behavior. False confidence from tests that pass on SQLite but would fail on Databricks. Inability to run the test suite against Databricks without extensive fixture rework.

**Prevention:**
1. Create a dialect-parameterized test fixture system. Tests that exercise dialect-agnostic behavior (e.g., "list_schemas returns a list") should run against multiple mock dialect configurations.
2. For Databricks-specific tests, create mock objects that return Databricks-shaped data (different type strings, no indexes, informational PKs). Do NOT require a live Databricks connection for unit tests.
3. Mark existing tests as `@pytest.mark.mssql` and new dialect-agnostic tests as `@pytest.mark.generic`. Databricks-specific tests get `@pytest.mark.databricks`.
4. The connection probe query must be dialect-specific. MSSQL: `SELECT @@VERSION`. Databricks: `SELECT current_catalog(), current_schema()`. Generic: `SELECT 1`.
5. Keep the existing 682+ tests UNTOUCHED initially. They validate MSSQL behavior and should continue to do so. Add new tests for new dialects; do not refactor existing tests to be generic.

**Detection:** Developer adds Databricks support, runs test suite, 682 tests pass. Manually connects to Databricks, first tool call fails. The tests gave false confidence.

**Phase:** Testing infrastructure setup (early). Dialect-parameterized fixtures should exist before writing Databricks-specific code.

---

### Pitfall 9: Identifier Quoting Varies By Dialect

**What goes wrong:** The codebase uses SQL Server bracket quoting `[identifier]` in:
- `metadata.py:365` for row count queries: `f'"{schema}"."{table_name}"'` (double-quotes in generic path, but brackets in MSSQL DMV queries)
- `column_stats.py:82`: `f"[{schema_name}].[{table_name}]"` (brackets always)
- `pk_discovery.py:39`: `f"[{schema_name}].[{table_name}]"` (brackets always)
- `fk_candidates.py:264-265`: `f"[{self.source_schema}].[{self.source_table}]"` (brackets always)

Databricks uses backticks: `` `schema`.`table` ``. PostgreSQL/ANSI uses double quotes: `"schema"."table"`. Using the wrong quoting style causes syntax errors.

Additionally, the `_sanitize_identifier` in `query.py` and the metadata-based identifier validation was designed for SQL Server identifier rules. Databricks identifiers allow different characters and have a 255-character limit.

**Why it happens:** Bracket quoting is a SQL Server-ism that leaked into raw SQL construction throughout the codebase.

**Prevention:**
1. The DialectStrategy must expose a `quote_identifier(name: str) -> str` method. MSSQL returns `[name]`, Databricks returns `` `name` ``, Generic returns `"name"`.
2. All f-string SQL construction that includes identifier quoting must use the dialect's quoter, not hardcoded brackets.
3. sqlglot can handle this via `exp.Column(this=exp.Identifier(this=name, quoted=True)).sql(dialect=target)`. Use sqlglot for identifier quoting in generated SQL rather than string formatting.
4. For the immediate term, ensure the generic metadata path (`_list_tables_generic`, `_get_row_count_generic`) uses double-quote quoting, which is ANSI-standard and works on most dialects including Databricks.

**Detection:** Run any query with qualified table names against Databricks. Bracket-quoted identifiers cause syntax errors.

**Phase:** Dialect strategy definition (early). Identifier quoting is needed by every module that generates SQL.

---

### Pitfall 10: TOML Config ConnectionConfig Is SQL Server-Shaped

**What goes wrong:** The current `ConnectionConfig` dataclass in `config.py` has fields specific to SQL Server: `server`, `database`, `port=1433`, `authentication_method="sql"`, `trust_server_cert`, `tenant_id`. A Databricks connection needs entirely different fields: `server_hostname`, `http_path`, `access_token` or OAuth credentials, `catalog`, `schema`. A PostgreSQL connection needs `host`, `port=5432`, `dbname`, `sslmode`.

If you add all possible fields to one `ConnectionConfig`, the dataclass becomes a grab-bag with most fields irrelevant for any given dialect. If you try to use the existing fields with different semantics (e.g., `server` = Databricks hostname), the field names are misleading and the defaults are wrong (`port=1433` for Databricks?).

**Why it happens:** The config model was designed for one dialect. Adding more dialects without restructuring creates a "universal config" anti-pattern.

**Prevention:**
1. Add a `dialect` discriminator field to the TOML config. Based on `dialect`, parse different field sets into different typed configs.
2. Use a union type / discriminated config: `MssqlConnectionConfig`, `DatabricksConnectionConfig`, `GenericConnectionConfig` (which just takes `sqlalchemy_url`).
3. The `_parse_connections` function in `config.py` should dispatch on `dialect` and validate fields appropriate for that dialect.
4. Existing configs without a `dialect` field default to `"mssql"` and parse with the current field set. Zero breaking changes.
5. For `GenericConnectionConfig`, the only required field is `sqlalchemy_url`. All other settings (pool size, etc.) are optional.

**Detection:** User adds a Databricks connection to TOML config and has to use `server` for the hostname and `database` for the catalog. Confusing and wrong defaults.

**Phase:** Connection config redesign (first phase). This is a prerequisite for all other dialect work.

---

## Minor Pitfalls

### Pitfall 11: Databricks PK/FK Discovery Returns Empty Results Without Error

**What goes wrong:** The PK discovery and FK candidate search modules use `INFORMATION_SCHEMA` queries to find constraints. On Databricks with Hive metastore, these queries return empty result sets (no error, just no rows). On Unity Catalog, `system.information_schema` exists but has a different schema than SQL Server's `INFORMATION_SCHEMA`. The tools silently return "no PK candidates found" when the reality is "this query cannot find PKs on this database."

**Prevention:** The DialectStrategy should report whether PK/FK constraint discovery is supported. When not supported, the tool response should say "PK constraint discovery is not available for Databricks (Hive metastore)" rather than silently returning empty results. For Unity Catalog, use `system.information_schema.table_constraints` with the correct column names.

**Phase:** Analysis module dialect support (later phase).

---

### Pitfall 12: Optional Dependency Groups Can Create Import-Time Crashes

**What goes wrong:** The plan calls for optional dependency groups (`mssql` extras require pyodbc, `databricks` extras require databricks-sql-connector + databricks-sqlalchemy). If a user installs `dbmcp[databricks]` but not `dbmcp[mssql]`, importing the MSSQL connection code will crash at `import pyodbc`. The current codebase imports pyodbc at module level in `connection.py:7`.

**Prevention:** 
1. Lazy imports for dialect-specific dependencies. `pyodbc` is imported inside `MssqlDialect`, not at module level. `databricks.sql` is imported inside `DatabricksDialect`.
2. Use `importlib.util.find_spec("pyodbc")` to check availability before importing, and raise a clear error: "pyodbc is required for MSSQL connections. Install with: pip install dbmcp[mssql]".
3. The MCP server should start successfully regardless of which optional deps are installed. Only fail when a user actually tries to connect to an unsupported dialect.

**Phase:** Package restructuring (early, alongside dependency group setup).

---

### Pitfall 13: sqlglot Transpilation Is Not Lossless

**What goes wrong:** The Tier 2 strategy relies on sqlglot to transpile standard SQL analysis queries to dialect-specific SQL. sqlglot transpilation has known gaps:
- Databricks-specific functions (`TRY_DIVIDE`, encryption functions, `UNIFORM`) may not transpile from ANSI.
- TSQL-specific functions (`ISNULL`, `DATEDIFF` with datepart) may not transpile cleanly to Databricks equivalents.
- Complex CTEs with window functions may produce syntactically correct but semantically different SQL across dialects.

For the analysis modules, this means a "generic" ANSI SQL query for column stats might transpile to invalid Databricks SQL if it uses `STDEV()` (SQL Server) instead of `STDDEV()` (ANSI/Databricks).

**Prevention:**
1. Write analysis queries in ANSI SQL to begin with, not TSQL. Transpile FROM ANSI TO target dialect, not from TSQL.
2. Test every transpiled query against each supported dialect (at minimum, verify it parses without error in sqlglot for that dialect).
3. For functions with no cross-dialect equivalent, use Tier 3 (dialect-specific) queries instead of trying to transpile.
4. Keep a registry of "known transpilation failures" and fall back to Tier 3 for those cases.

**Phase:** Analysis module refactoring (later phase). Must be validated empirically, not assumed to work.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Connection config redesign | Breaking interface (Pitfall 5), SQL Server-shaped config (Pitfall 10) | Support both old and new interfaces; discriminated config with dialect field; default to mssql |
| Dialect strategy protocol | Inspector shape differences (Pitfall 1), identifier quoting (Pitfall 9) | Capability flags in protocol; dialect-owned quoting; wrap Inspector calls |
| Databricks dialect impl | Three-level namespace (Pitfall 2), connection lifecycle (Pitfall 7), non-SQLAlchemy exceptions (Pitfall 6) | Catalog-aware model; dialect-owned engine creation; exception normalization |
| Query validation dialect support | sqlglot dialect mismatch (Pitfall 4) | Add dialect param to validate_query; use connection's dialect |
| Analysis module refactoring | Hardcoded SQL Server syntax (Pitfall 3), PK/FK empty results (Pitfall 11), transpilation gaps (Pitfall 13) | Three-tier query strategy; capability matrix; ANSI SQL as base |
| Test infrastructure | Test suite assumes SQL Server (Pitfall 8) | Dialect-parameterized fixtures; keep existing tests; add new per-dialect |
| Package restructuring | Import-time crashes (Pitfall 12) | Lazy imports; clear error messages for missing optional deps |
| connect_database interface | Breaking change (Pitfall 5) | Backward-compatible: old params still work; new sqlalchemy_url is additive |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ConnectionManager + Databricks | Using ODBC connection string builder for HTTP-based Databricks connections | DialectStrategy owns engine creation; MSSQL builds ODBC strings, Databricks builds SQLAlchemy URLs directly |
| MetadataService + Databricks Inspector | Catching only SQLAlchemyError when databricks-sqlalchemy raises TypeError/NotImplementedError | Widen exception handling or normalize through dialect strategy |
| validate_query + non-TSQL queries | Parsing all queries as TSQL dialect regardless of connection | Pass dialect from connection to validation; store dialect on connection metadata |
| column_stats + Databricks | Using `SELECT TOP N`, `[bracket]` quoting, `DATEDIFF(datepart, ...)`, `LEN()` against Databricks | Use sqlglot transpilation or dialect-specific query templates; `LIMIT N`, backtick quoting, `LENGTH()` |
| TOML config + new dialects | Adding Databricks fields to existing ConnectionConfig (god object) | Discriminated union: dialect field determines which config dataclass is instantiated |
| Analysis tools + Unity Catalog vs Hive | Assuming `INFORMATION_SCHEMA` exists on all Databricks connections | Check catalog type; Unity Catalog has `system.information_schema`; Hive has neither |
| test_connection probe + Databricks | Running `SELECT @@VERSION, DB_NAME()` on Databricks (SQL Server-only functions) | Dialect-specific probe queries; Databricks: `SELECT 1` or `SELECT current_catalog()` |
| Azure AD auth + Databricks OAuth | Treating all token auth the same (pyodbc attrs_before vs HTTP headers) | Completely separate auth paths per dialect; no shared token infrastructure |

## Sources

- Direct codebase inspection: `src/db/connection.py` (ODBC-specific engine creation), `src/db/metadata.py` (dual MSSQL/generic paths, Inspector usage), `src/db/validation.py` (hardcoded tsql dialect), `src/analysis/column_stats.py` (SQL Server syntax throughout), `src/analysis/fk_candidates.py` (INFORMATION_SCHEMA + sys.indexes), `src/analysis/pk_discovery.py` (INFORMATION_SCHEMA), `src/config.py` (SQL Server-shaped ConnectionConfig), `src/mcp_server/schema_tools.py` (connect_database interface)
- Databricks SQLAlchemy dialect: databricks-sqlalchemy v2.0.9 README (HIGH confidence -- official docs: no LargeBinary, no Enum, no enforced FKs, backtick quoting, Identity only on BigInteger)
- Databricks Unity Catalog: Databricks docs (HIGH confidence -- three-level namespace, informational-only PK/FK constraints, requires Runtime 11.3+, `RELY` requires Photon + Runtime 14.2+)
- databricks-sql-connector issues: GitHub (MEDIUM confidence -- 83 open issues including session init failures, rate limiting, slow batch operations, SSL warnings)
- databricks-sqlalchemy issues: GitHub (MEDIUM confidence -- cross-catalog query issues, UUID handling broken, missing INTERVAL/VARIANT/JSON type support)
- sqlglot Databricks dialect: sqlglot docs (HIGH confidence -- `COLON_IS_VARIANT_EXTRACT`, `STRICT_CAST`, backtick identifiers, DATEADD/DATEDIFF differences from TSQL)
- SQLAlchemy Inspector docs: "Dialect is given a chance to provide dialect-specific Inspector instance" -- dialect-specific behavior is expected and documented as "consult dialect docs" (HIGH confidence)

---
*Pitfalls research for: dbmcp v2.0 Multi-Dialect Support*
*Researched: 2026-04-13*
