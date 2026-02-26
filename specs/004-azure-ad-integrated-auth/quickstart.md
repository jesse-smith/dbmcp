# Quickstart: Azure AD Integrated Authentication

**Date**: 2026-02-26
**Feature**: 004-azure-ad-integrated-auth

## Overview

This feature adds `azure_ad_integrated` as a new authentication method for connecting to Azure SQL databases. It uses token-based authentication via the `azure-identity` library, bypassing the ODBC driver's built-in Azure AD auth (which has known issues with Private Link DNS resolution).

## Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `azure-identity>=1.14.0` to core dependencies |
| `src/models/schema.py` | Add `AZURE_AD_INTEGRATED = "azure_ad_integrated"` to `AuthenticationMethod` enum |
| `src/db/connection.py` | Add `tenant_id` parameter, token acquisition logic, `creator` function for SQLAlchemy engine, updated ODBC string builder |
| `src/mcp_server/server.py` | Add `tenant_id` parameter to `connect_database` tool, update auth method validation message |
| `tests/unit/test_connection.py` | Add tests for new auth method: validation, ODBC string, token packing, creator function |

## Files to Create

| File | Purpose |
|------|---------|
| `src/db/azure_auth.py` | Token acquisition module: `AzureTokenProvider` class wrapping `DefaultAzureCredential` + token packing logic |

## Key Design Decisions

1. **Separate module for token logic** (`azure_auth.py`): Keeps `connection.py` focused on connection management. The token provider handles credential chain setup, token acquisition, and struct packing.

2. **`creator` function pattern**: SQLAlchemy's `create_engine(creator=...)` is used instead of URL-based connection. The creator acquires a fresh token on each new physical connection, providing automatic token refresh.

3. **`pool_pre_ping=True` + `pool_recycle=3600`**: Already the project defaults. Together with the `creator` pattern, this ensures connections are refreshed before tokens expire.

## Implementation Order

1. Add dependency (`pyproject.toml`)
2. Add enum value (`schema.py`)
3. Create token provider (`azure_auth.py`)
4. Update connection manager (`connection.py`)
5. Update MCP tool (`server.py`)
6. Add tests (unit + integration)
