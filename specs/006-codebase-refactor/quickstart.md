# Quickstart: Codebase Refactor

**Feature**: 006-codebase-refactor

## Prerequisites

- Python 3.11+
- uv package manager
- All existing tests passing: `uv run pytest tests/`

## Before Starting

1. Record baseline metrics:
   ```bash
   # Source line count
   find src/ -name '*.py' | xargs wc -l | tail -1

   # Test count
   uv run pytest tests/ --co -q | tail -1

   # Coverage baseline
   uv run pytest tests/ --cov=src --cov-report=term-missing -q
   ```

2. Verify branch:
   ```bash
   git branch --show-current  # Should be 006-codebase-refactor
   ```

## Verification After Each Phase

```bash
# Tests pass
uv run pytest tests/

# Linter clean
uv run ruff check src/ tests/

# No circular imports
uv run python -c "import src.mcp_server.server"
```

## Verification for Hidden Tools

```bash
# After refactoring, uncomment each hidden tool decorator one at a time and verify:
uv run python -c "import src.mcp_server.server"
# Then re-comment before moving to the next
```
