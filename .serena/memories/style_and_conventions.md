# Code Style & Conventions

## Python
- Python 3.11+ features allowed (match/case, PEP 604 unions, etc.)
- Follows standard PEP 8 via ruff (line-length 120)
- Type hints expected; pyright is configured
- Use `from __future__ import annotations` where helpful for forward refs

## Ruff Rules (selected)
- `E`, `W` (pycodestyle), `F` (pyflakes), `I` (isort), `B` (bugbear), `C4` (comprehensions), `UP` (pyupgrade)
- **Ignored**: `E501` (handled by formatter), `B008` (function calls in arg defaults — allowed for FastAPI-style deps)
- isort: `src` is known-first-party

## Naming
- snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants
- MCP tool functions registered via `@mcp.tool()` decorator in tool modules

## Data Libraries
- **Polars is the default** for DataFrames — NOT Pandas (unless absolutely necessary)
- SQLAlchemy 2.0 style (not legacy 1.x)

## Response Format
- All MCP tool responses use **TOON format** (token-efficient)
- TOON uses `:` for key-value (like YAML), NOT `=`
- Bare string values (no quotes), compact array notation

## Testing conventions
- Test files: `test_*.py`, classes `Test*`, functions `test_*`
- asyncio_mode = auto
- Tests organized by kind under `tests/unit/`, `tests/integration/`, `tests/compliance/`, `tests/performance/`, `tests/staleness/`
- Coverage gate: `fail_under = 85`
- Follow red-green-refactor TDD: write tests before implementation
- Prefer fewer well-designed tests over shallow coverage

## Engineering Philosophy
- KISS, DRY, YAGNI, Rule of Three (don't abstract until pattern appears 3x)
- Simplicity in user-facing design — prefer approaches easier to explain
- Explicit over implicit; fail fast; immutability by default
- Composition over inheritance; dependency inversion; loose coupling
