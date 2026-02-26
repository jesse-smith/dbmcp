# Contract: connect_database MCP Tool (Updated)

**Date**: 2026-02-26
**Feature**: 004-azure-ad-integrated-auth

## Tool Signature Changes

### New/Modified Parameters

| Parameter | Type | Default | Change |
|-----------|------|---------|--------|
| `authentication_method` | `str` | `"sql"` | **Modified**: Now accepts `'azure_ad_integrated'` in addition to `'sql'`, `'windows'`, `'azure_ad'` |
| `tenant_id` | `str \| None` | `None` | **New**: Optional Azure AD tenant ID for `azure_ad_integrated` auth |

### Unchanged Parameters

`server`, `database`, `username`, `password`, `port`, `trust_server_cert`, `connection_timeout` — no changes.

## Behavior by Authentication Method

### `azure_ad_integrated` (new)

**Input**: `server`, `database`, `port`, `trust_server_cert`, `connection_timeout`, optionally `tenant_id`
**Ignored**: `username`, `password` (if provided)

**Success response** (same shape as existing):
```json
{
  "connection_id": "a1b2c3d4e5f6",
  "status": "connected",
  "message": "Successfully connected to mydb",
  "schema_count": 5,
  "has_cached_docs": false
}
```

**Auth failure response**:
```json
{
  "status": "failed",
  "message": "Azure AD authentication failed: No credential sources available. Run 'az login' or set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID environment variables."
}
```

**Invalid method response** (updated):
```json
{
  "status": "failed",
  "message": "Invalid authentication_method 'xyz'. Use 'sql', 'windows', 'azure_ad', or 'azure_ad_integrated'."
}
```

## Backward Compatibility

- All existing auth methods behave identically
- `tenant_id` parameter is ignored for non-`azure_ad_integrated` methods
- Response shape is unchanged
- No breaking changes to existing clients
