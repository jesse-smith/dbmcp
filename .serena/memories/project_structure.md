# Codebase Structure

```
src/
  __init__.py
  config.py              # TOML config loading
  logging_config.py
  serialization.py       # TOON serialization helpers
  type_registry.py
  mcp_server/
    server.py            # main() entrypoint, MCP server bootstrap
    schema_tools.py      # connect_database, list_schemas, list_tables, get_table_schema, get_sample_data
    query_tools.py       # execute_query
    analysis_tools.py    # get_column_info, find_pk_candidates, find_fk_candidates
  db/
    connection.py        # connection pooling / management
    metadata.py          # schema introspection
    query.py             # query execution + row limiting
    validation.py        # sqlglot-based denylist validation
    azure_auth.py        # Azure AD integrated auth
    dialects/            # dialect-specific adapters (mssql, databricks, sqlite)
  analysis/
    column_stats.py
    pk_discovery.py
    fk_candidates.py
    _sql.py
  models/
    schema.py            # schema-related dataclasses/models
    analysis.py
    relationship.py

tests/
  conftest.py            # shared fixtures
  helpers.py
  utils.py
  unit/
  integration/
  compliance/
  performance/
  staleness/
  examples/
  fixtures/

specs/                   # speckit feature specs (per-feature dirs + STATUS.md registry)
docs/
examples/                # Jupyter notebooks
scripts/
.planning/               # GSD planning artifacts
.specify/                # speckit config
```

## Key config files
- `pyproject.toml` — deps, ruff config, pytest markers, coverage gates
- `.mcp.json` — MCP server config
- `CLAUDE.md` — project instructions
- `specs/STATUS.md` — feature registry
