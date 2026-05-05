---
id: 260504-ilw
type: quick
status: complete
description: Centralize log file to ~/.dbmcp/logs/ with rotation and auto-migration
date: 2026-05-05
---

# Quick Task 260504-ilw — Summary

Moved dbmcp log output out of the working directory and into a centralized,
per-project location under `~/.dbmcp/logs/`. Added file rotation and a one-shot
auto-migration that moves any existing `./dbmcp.log` into the new location on
first startup.

## What changed

| File | Change |
|------|--------|
| `src/logging_config.py` | Rewrote `setup_logging`: new default path, `RotatingFileHandler`, legacy migration helper |
| `src/config.py` | Added `LoggingConfig` dataclass, `[logging]` parser, `AppConfig.logging` field |
| `src/mcp_server/server.py` | Updated single call site to use `log_dir` from config; removed hardcoded `Path("dbmcp.log")` |
| `tests/unit/test_logging_config.py` | New — 12 tests (path shape, hash stability, rotation, migration, errors) |
| `.gitignore` | Removed `dbmcp.log` entry (nothing writes to CWD anymore) |

## Behavior

**Default path:** `~/.dbmcp/logs/<cwd-basename>-<8char-blake2b-of-abs-path>.log`
- Example: `/Users/alice/work/dbmcp` → `~/.dbmcp/logs/dbmcp-a3f1c92e.log`
- Two projects named `dbmcp` in different paths produce different hashes; no collisions.

**Rotation:** `RotatingFileHandler(maxBytes=5_000_000, backupCount=1)` — caps disk per project at ~10 MB.

**Override:** `[logging] dir = "/some/path"` in `dbmcp.toml` or `~/.dbmcp/config.toml` redirects the log directory. The hashed filename scheme still applies inside the override directory. No env vars introduced.

**Auto-migration (temporary — `# TODO: remove after v2.1`):** If `./dbmcp.log` exists at startup, its contents are appended to the new centralized path and the legacy file is deleted. One INFO line announces the migration. Errors during migration are swallowed and logged at WARNING — never breaks startup.

## Decisions honored from discussion

- No `DBMCP_LOG_FILE` / `DBMCP_LOG_DIR` env vars — project stance is TOML-only.
- No "one big file for everything" mode — YAGNI, dropped.
- Rotation kept (not single-file-with-truncate) because Python stdlib doesn't support the latter cleanly.
- `~/.dbmcp/logs/` (not `platformdirs`) — matches existing `~/.dbmcp/config.toml` precedent.
- Migration marked temporary with inline TODO.

## Verification

- `uv run pytest tests/unit/test_logging_config.py` — 12/12 pass
- `uv run pytest tests/unit/test_config.py tests/unit/test_logging_config.py` — 67/67 pass
- `uv run pytest` full suite — 909 pass, 78 skip, 6 pre-existing Azure AD integration failures (live network, unrelated)
- `uv run ruff check` — clean on all changed files

## Follow-ups (not in scope)

- Consider `dbmcp logs` subcommand if centralized logs become painful to manage
- Remove legacy-migration code after v2.1 (see TODO comment)
- `[logging] level` config override (skippable until someone asks)
