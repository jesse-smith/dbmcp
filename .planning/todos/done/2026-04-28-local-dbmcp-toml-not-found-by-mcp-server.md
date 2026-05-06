---
created: 2026-04-28T15:52:59.518Z
resolved: 2026-04-28
resolved_by: quick task 260428-fr7
title: Local dbmcp.toml not found by MCP server
area: database
files:
  - src/config/loader.py
  - README.md:105-110
---

## Resolution (2026-04-28)

Original diagnosis was incorrect. Config discovery (`_find_config_file` in
`src/config.py`) works correctly — both `./dbmcp.toml` and
`~/.dbmcp/config.toml` were being found. The actual root cause was a silent
parse failure: `load_config()` caught the validation error (missing required
`dialect` field introduced by the v2.0 multi-dialect branch), logged a
`warning` (invisible to MCP clients), and returned an empty `AppConfig()`.
`connect_database` then reported the misleading `Available: none`.

Fixed in quick task **260428-fr7**:
- `AppConfig.load_error` now captures parse exceptions.
- `connect_database` branches on `config.load_error` before the name-lookup
  and surfaces the real error to the client.

See `.planning/quick/260428-fr7-surface-config-parse-failures-to-the-mcp/`.

## Problem

The MCP server does not discover a project-level `./dbmcp.toml` placed in the project root. Symptom: after writing `dbmcp.toml` at the project root (`/Users/jsmith79/Documents/Projects/Ongoing/dbmcp/dbmcp.toml`) and reconnecting the MCP, `connect_database(connection_name="stemsoft")` still returns `"Named connection 'stemsoft' not found in config. Available: none"`. Copying the same content to `~/.dbmcp/config.toml` is the only way to get the named connection recognized.

README.md:110 states the project-level config should be picked up from "the directory where the MCP server runs (usually your project root)." Either:
- The MCP server process CWD is not the project root (so relative `./dbmcp.toml` lookup misses), or
- The config loader is not checking the project-level path at all, or
- Docs are wrong about the lookup location.

This directly blocks UAT for phase 11 and contradicts the documented Config Precedence ladder (#1 project-level should win).

## Solution

TBD. Candidates:
1. Make the loader search upward from CWD for a `dbmcp.toml` (like git does for `.git`), bounded to a reasonable number of parents.
2. Resolve `dbmcp.toml` relative to a known anchor (e.g., the directory of the first `pyproject.toml` discovered upward) instead of trusting CWD.
3. Accept an explicit `DBMCP_CONFIG` env var as an override.
4. If behavior is intentional, update README to clarify that only user-level `~/.dbmcp/config.toml` is reliable when CWD is not guaranteed (and name a canonical way to launch the server from the project root).

Reproduction: from project root, `dbmcp.toml` with `[connections.stemsoft]`, restart MCP, call `connect_database(connection_name="stemsoft")` — expect connect, actual "not found."
