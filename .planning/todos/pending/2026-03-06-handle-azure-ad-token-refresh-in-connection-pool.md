---
created: 2026-03-06T18:47:44.210Z
title: Handle Azure AD token refresh in connection pool
area: database
files:
  - src/db/connection.py:26-41
  - src/db/connection.py:66-74
---

## Problem

SQLAlchemy connection pooling reuses connections from the pool, but Azure AD authentication tokens expire (typically after 1 hour). When a pooled connection's token expires, the next query using that connection gets an "invalid token" error mid-request.

The current `PoolConfig` is set once at `ConnectionManager` creation (singleton) with no mechanism to detect or handle stale tokens on checkout from the pool.

## Solution

1. **Enable `pool_pre_ping`** in SQLAlchemy engine creation — this tests connections before checkout, detecting stale ones
2. **Implement token refresh** before pool connection checkout — use `azure-identity`'s `DefaultAzureCredential` to get fresh tokens and inject them via a connection event listener
3. **Add a custom pool event** on `checkout` that validates token expiry time and refreshes if within a threshold (e.g., 5 minutes before expiry)
4. **Consider per-connection pool config** — Azure SQL may need different pool settings (larger pool, shorter recycle time) than on-prem SQL Server with Windows auth
