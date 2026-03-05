---
phase: quick-4
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - README.md
autonomous: true
requirements:
  - QUICK-4

must_haves:
  truths:
    - "README accurately describes what dbmcp does (database exploration + query + analysis for AI agents)"
    - "README install instructions use uv (not pip/venv)"
    - "README MCP tools table lists exactly the 9 current tools"
    - "README project structure matches actual src/ layout"
    - "README is concise — no speculative NFR tables or placeholder sections"
  artifacts:
    - path: "README.md"
      provides: "Accurate project documentation"
      contains: "uv"
  key_links:
    - from: "README.md"
      to: "pyproject.toml"
      via: "Install instructions reference uv and entry point"
      pattern: "uv.*install|dbmcp"
---

<objective>
Rewrite README.md to accurately reflect the current state of the dbmcp project.

Purpose: The existing README is outdated — wrong tools list, pip-based install, missing features (Azure AD auth, CTE support, query validation, TOON format), fictional project structure. A correct README prevents confusion for users and AI agents consuming this repo.

Output: Updated README.md
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@README.md
@pyproject.toml
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite README.md to reflect current project</name>
  <files>README.md</files>
  <action>
Rewrite README.md with the following sections. Keep it concise — no filler, no speculative content.

**Title and badges:** Keep existing CI and codecov badges. Change title/description:
- Title: "DBMCP: Database MCP Server for SQL Server"
- Description: MCP server that gives AI assistants full read-only access to SQL Server databases — schema exploration, query execution, and structural analysis. Designed for legacy databases with undeclared foreign keys. All responses use TOON format for minimal token consumption.

**Features** (brief bullet list, no sub-bullets):
- Schema exploration (schemas, tables, columns, indexes, constraints)
- Read-only query execution with CTE support and automatic row limiting
- Query validation via configurable denylist (sqlglot-based)
- Primary key candidate discovery
- Foreign key candidate inference
- Column statistics and analysis
- Azure AD integrated authentication
- TOON-formatted responses (token-efficient for LLM consumers)
- Async database execution with configurable query timeouts

**Requirements:**
- Python 3.11+
- SQL Server (via ODBC Driver 18)
- uv (Python package manager)
- MCP-compatible client (Claude Desktop, Claude Code, etc.)

**Installation** — two methods:

1. Global install (recommended for MCP clients):
```bash
uv tool install "dbmcp @ git+https://github.com/jesse-smith/dbmcp.git"
```

2. Local development:
```bash
git clone https://github.com/jesse-smith/dbmcp.git
cd dbmcp
uv sync
```

Include ODBC Driver 18 install instructions (keep existing macOS/Linux/Windows sections — they are still correct).

**MCP Client Configuration** — show Claude Desktop and Claude Code configs:

Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "dbmcp"
    }
  }
}
```

Claude Code (`.mcp.json` or via CLI):
```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "dbmcp",
      "type": "stdio"
    }
  }
}
```

Note: If installed locally (not via `uv tool`), use `uv run dbmcp` as the command and set `cwd` to the repo directory.

**MCP Tools Reference** — table with exactly these 9 tools:

| Tool | Description |
|------|-------------|
| `connect_database` | Connect to a SQL Server instance (Windows auth, SQL auth, or Azure AD) |
| `list_schemas` | List all schemas with table/view counts |
| `list_tables` | List tables with filtering, sorting, and pagination |
| `get_table_schema` | Get detailed table schema (columns, indexes, foreign keys) |
| `get_sample_data` | Retrieve sample rows from a table |
| `execute_query` | Execute read-only SQL queries (supports CTEs) |
| `get_column_info` | Get column-level statistics and value distributions |
| `find_pk_candidates` | Discover likely primary key columns via uniqueness analysis |
| `find_fk_candidates` | Infer potential foreign key relationships between tables |

**Development** section (concise):
```bash
uv sync --group dev
uv run pytest tests/
uv run ruff check src/
```

**Project Structure** — actual layout:
```
dbmcp/
  src/
    mcp_server/    # FastMCP server, tool definitions
    db/            # Connection, metadata, query execution, validation
    analysis/      # PK discovery, FK inference, column stats
    models/        # Data models (schema, relationship, analysis)
  tests/
    unit/
    integration/
    compliance/
    performance/
  specs/           # Feature specifications
```

**License:** MIT

Do NOT include: NFR table, Contributing placeholder, Usage examples with natural language prompts (the tools table is sufficient), any placeholder text like "[Your X Here]".
  </action>
  <verify>
    <automated>grep -c "uv" README.md | xargs test 3 -le && grep -q "find_fk_candidates" README.md && grep -q "find_pk_candidates" README.md && grep -q "TOON" README.md && grep -q "MIT" README.md && echo "PASS" || echo "FAIL"</automated>
  </verify>
  <done>README.md accurately reflects current project: 9 tools listed, uv-based install, correct project structure, Azure AD and TOON mentioned, no outdated/placeholder content</done>
</task>

</tasks>

<verification>
- README mentions all 9 current tools (connect_database, list_schemas, list_tables, get_table_schema, get_sample_data, execute_query, get_column_info, find_pk_candidates, find_fk_candidates)
- README does NOT mention removed tools (infer_relationships, analyze_column, export_documentation, load_cached_docs, check_drift)
- Install instructions use `uv`, not `pip` or manual venv
- Project structure matches actual directories (no inference/, cache/)
- No placeholder text ("[Your X Here]")
</verification>

<success_criteria>
README.md is concise, accurate, and reflects the current state of dbmcp including all 9 tools, uv-based installation, TOON format, Azure AD auth, and correct project structure.
</success_criteria>

<output>
After completion, create `.planning/quick/4-update-readme-to-reflect-current-project/4-SUMMARY.md`
</output>
