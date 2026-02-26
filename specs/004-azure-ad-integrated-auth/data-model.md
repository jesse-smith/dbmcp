# Data Model: Azure AD Integrated Authentication

**Date**: 2026-02-26
**Feature**: 004-azure-ad-integrated-auth

## Entity Changes

### AuthenticationMethod (modified)

Existing enum extended with one new value.

| Value | Description | Requires Credentials | New? |
|-------|-------------|---------------------|------|
| `sql` | SQL Server authentication | username + password | No |
| `windows` | Windows integrated auth | None (OS credentials) | No |
| `azure_ad` | Azure AD password auth | username + password | No |
| `azure_ad_integrated` | Azure AD integrated auth (token-based) | None (credential chain) | **Yes** |

### Connection (unchanged)

No structural changes. For `azure_ad_integrated` connections:
- `username`: `None` (no username provided)
- `authentication_method`: `AuthenticationMethod.AZURE_AD_INTEGRATED`
- All other fields unchanged

### ConnectionManager.connect() (modified signature)

New optional parameter:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tenant_id` | `str \| None` | `None` | Azure AD tenant ID. Only used with `azure_ad_integrated`. If omitted, uses the default tenant from the credential chain. |

## Validation Rules

- `azure_ad_integrated` auth method MUST NOT require `username` or `password`
- If `username`/`password` are provided with `azure_ad_integrated`, they are ignored (not an error)
- `tenant_id` is only meaningful for `azure_ad_integrated`; ignored for other auth methods
- `tenant_id` format: UUID string (e.g., `"12345678-1234-1234-1234-123456789012"`) or domain (e.g., `"contoso.onmicrosoft.com"`)

## Connection String Differences

For `azure_ad_integrated`, the ODBC connection string differs from all other methods:
- Does NOT include `UID`, `PWD`, or `Authentication` keywords
- Token is passed via connection attribute, not connection string
- Connection string only contains: Driver, Server, Database, TrustServerCertificate, Connection Timeout
