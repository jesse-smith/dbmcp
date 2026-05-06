---
id: 260504-ilw
type: quick
status: in-progress
description: Centralize log file to ~/.dbmcp/logs/ with rotation and auto-migration
date: 2026-05-05
must_haves:
  truths:
    - "dbmcp no longer writes dbmcp.log to CWD"
    - "Default log path is ~/.dbmcp/logs/<cwd-basename>-<8char-hash>.log"
    - "Hash is blake2b(abs_cwd.encode(), digest_size=4).hexdigest() — stable across runs in same dir, distinct across dirs"
    - "Log rotation bounded at ~10MB per project (RotatingFileHandler maxBytes=5_000_000, backupCount=1)"
    - "Optional [logging] dir override in dbmcp.toml / ~/.dbmcp/config.toml"
    - "One-time auto-migration: if ./dbmcp.log exists at startup, append its contents to the new log path and delete it. Marked as temporary (TODO: remove after v2.1)"
    - "No new env vars introduced (project stance: env vars only for ${VAR} interpolation inside TOML)"
  artifacts:
    - src/logging_config.py (rewritten)
    - src/config.py (LoggingConfig dataclass, [logging] parser)
    - src/mcp_server/server.py (call-site updated)
    - tests/unit/test_logging_config.py (new)
    - .gitignore (dbmcp.log entry removed)
  key_links:
    - src/logging_config.py:12 (DEFAULT_LOG_FILE — being replaced)
    - src/mcp_server/server.py:23 (single call site)
    - src/config.py:155 (existing ~/.dbmcp/ precedent)
---

# Centralize log file to ~/.dbmcp/logs/ with rotation and auto-migration

## Background

`dbmcp.log` is currently written to CWD (`src/mcp_server/server.py:23`). User installs dbmcp at the user level, so every project directory gets one — requiring repeated `.gitignore` edits. User wants logs centralized, discoverable by project name, collision-safe, and size-bounded.

Shape was agreed in discussion before this plan was written:
- Location: `~/.dbmcp/logs/` (nests under existing `~/.dbmcp/` used by `config.toml`)
- Filename: `<cwd-basename>-<8char-blake2b-hash-of-abs-path>.log`
- Rotation: `RotatingFileHandler(maxBytes=5_000_000, backupCount=1)` → ~10MB cap
- Override: `[logging] dir = "..."` in TOML (no env vars — project precedent)
- Auto-migration: one-shot move of `./dbmcp.log` → new path on startup, with `# TODO: remove after v2.1`

## Tasks

### Task 1: `src/config.py` — add `LoggingConfig`

- New frozen dataclass `LoggingConfig(dir: Path | None = None)`
- Add `logging: LoggingConfig = field(default_factory=LoggingConfig)` to `AppConfig`
- Extend `_parse_config` to read `raw.get("logging", {})`, pull `dir` if present, expand `~`/env-vars via `Path(str).expanduser()`
- No new imports needed (Path already imported)

**Verify**: `AppConfig().logging.dir is None`; TOML `[logging]\ndir = "~/foo"` → `logging.dir == Path.home()/"foo"`

### Task 2: `src/logging_config.py` — rewrite

Replace hardcoded `DEFAULT_LOG_FILE = Path("dbmcp.log")` with:

- `_compute_default_log_path(dir_override: Path | None = None) -> Path`:
  - base = `dir_override or Path.home() / ".dbmcp" / "logs"`
  - cwd = `Path.cwd().resolve()`
  - hash = `hashlib.blake2b(str(cwd).encode(), digest_size=4).hexdigest()` → 8 chars
  - return `base / f"{cwd.name}-{hash}.log"`

- `_migrate_legacy_log(new_path: Path) -> None`:
  - TEMPORARY: remove after v2.1 (TODO comment)
  - If `./dbmcp.log` exists and is a file, append contents to `new_path` (creating parent dirs), then delete the legacy file
  - Log a single INFO line: `"Migrated legacy log file ./dbmcp.log -> <new_path>"`
  - Wrap in `try/except Exception` — swallow and log at WARNING; migration must never break startup

- `setup_logging(log_dir: Path | None = None, ...)`:
  - Changed signature: `log_dir` replaces `log_file` (simpler — caller doesn't pick filename)
  - Still supports `log_file=None` equivalent via `log_to_file=False` flag for tests
  - Compute path, ensure parent dir exists, migrate legacy, then attach `RotatingFileHandler(maxBytes=5_000_000, backupCount=1)`

**Verify**: two different CWDs produce different filenames; same CWD produces same filename across runs; rotation kicks in at 5MB; migration appends+deletes; `dir_override` honored.

### Task 3: `src/mcp_server/server.py` — update call site

Change:
```python
logger = setup_logging(log_file=Path("dbmcp.log"), log_to_stderr=True)
```
to:
```python
_bootstrap_cfg = load_config()  # note: will log to stderr only until setup_logging runs
logger = setup_logging(log_dir=_bootstrap_cfg.logging.dir, log_to_stderr=True)
```

Note: `load_config()` calls `logger.info` internally via the module-level logger. Before `setup_logging` runs, the logger has no handlers → log lines are dropped (per Python's `lastResort` handler). This is acceptable for startup noise. After `setup_logging` runs, a second `load_config()` call is NOT made — config is loaded once, both times it would log "Config loaded from …" which is fine to lose pre-setup. If we want the first load logged, can re-emit a line post-setup. Keep it simple: don't re-emit.

**Verify**: server starts without `dbmcp.log` appearing in CWD; log lines appear in `~/.dbmcp/logs/dbmcp-<hash>.log`.

### Task 4: `tests/unit/test_logging_config.py` — new

Cases:
1. `test_default_path_uses_cwd_basename` — monkeypatch `Path.cwd` + `Path.home`, assert filename shape `<basename>-<8hex>.log`
2. `test_hash_stable_for_same_cwd` — same cwd → identical hash across calls
3. `test_hash_differs_for_different_cwds` — `/foo/dbmcp` vs `/bar/dbmcp` produce different hashes
4. `test_dir_override_respected` — pass `log_dir=tmp_path/"logs"` → log file under that dir
5. `test_rotation_triggers_at_5mb` — write >5MB, assert `.log.1` created, main file <= 5MB
6. `test_migration_moves_and_deletes` — create `./dbmcp.log` with known content in tmp_path, run setup, assert new path contains content and old file is gone
7. `test_migration_idempotent` — second setup run (no legacy file) is a no-op, doesn't error
8. `test_migration_swallows_errors` — make legacy file unreadable (chmod 000 or patch), assert setup still returns a logger

Uses `tmp_path` fixture + `monkeypatch` to redirect `Path.home()` and `Path.cwd()`.

### Task 5: `.gitignore` — remove `dbmcp.log` entry

Delete lines 57-58 (the `# MCP server logs` header + `dbmcp.log` entry). No project writes to CWD anymore.

### Task 6: Verify

- `uv run pytest tests/` — existing tests pass + new tests pass
- `uv run ruff check src/ tests/` — clean

## Out of scope

- `DBMCP_LOG_FILE` / `DBMCP_LOG_DIR` env vars (rejected in discussion — project uses TOML)
- One-file-for-everything mode (`[logging] file`) — YAGNI, rejected
- Log level config (`[logging] level`) — can add later if asked
- Cross-platform `platformdirs` — not needed; `~/.dbmcp/` already used
- Cleanup/pruning of stale logs across long-abandoned projects — user's job; can add `dbmcp logs` subcommand later if painful
