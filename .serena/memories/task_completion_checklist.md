# Task Completion Checklist

Before marking a task complete:

## 1. Tests
```bash
uv run pytest tests/
```
- Full suite must pass (or at minimum, the relevant scope)
- Coverage gate: `fail_under = 85` (configured in pyproject.toml)
- If feature branch: ensure new code has tests following red-green-refactor TDD

## 2. Lint — zero warnings
```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```
- Known pre-existing warning: `src/metrics.py` has a Generator import from typing instead of collections.abc — not introduced by new work.

## 3. Type check
```bash
uv run pyright
```

## 4. Complexity (if applicable)
```bash
uv run complexipy src/
```

## 5. Commit granularity
- One commit per logical task (not per file)
- Verify on the correct branch before committing — never switch to main mid-task

## 6. Feature completion (on merge to main)
- Run `/speckit.complete` — updates completion headers in spec.md/plan.md/tasks.md and `specs/STATUS.md` registry
- Commit the status updates

## 7. Git auth (for push/PR)
- Verify `gh auth status` succeeds before any push/PR/GitHub API operation
