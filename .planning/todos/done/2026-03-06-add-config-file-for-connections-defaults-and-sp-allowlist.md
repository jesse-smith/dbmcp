---
created: 2026-03-06T18:50:22.303Z
title: Add config file for connections, defaults, and SP allowlist
area: general
files:
  - src/db/connection.py:26-41
  - src/db/validation.py:41-67
  - src/mcp_server/server.py
---

## Problem

Several things are currently hardcoded that should be configurable:

1. **Connection details**: Users must pass server/database/auth params via `connect_database` tool every time. No way to define default or named connections.
2. **Default parameters**: Row limits (10k), sample sizes (1k), text truncation (1000 chars), pool config — all hardcoded constants with no override mechanism.
3. **Stored procedure allowlist**: 22 safe SPs are in a `frozenset` in `validation.py`. No way to extend for custom DBs or new SQL Server versions without code changes.

This makes the tool less usable for environments with multiple databases, custom procedures, or non-default needs.

## Solution

Add a TOML or YAML config file (e.g., `~/.dbmcp/config.toml` or `dbmcp.toml` in project root) supporting:

```toml
[defaults]
row_limit = 10000
sample_size = 1000
text_truncation = 1000

[connections.clinic]
server = "SVWTSTEM04"
database = "StemSoftClinic"
auth = "windows"
trust_server_cert = true

[connections.azure]
server = "myserver.database.windows.net"
database = "MyDb"
auth = "azure_ad"

[validation]
additional_safe_procedures = ["sp_custom_report", "sp_dashboard_data"]
```

Load at server startup with environment variable override (`DBMCP_CONFIG`). Fall back to sensible defaults if no config file exists.
