# Research: Azure AD Integrated Authentication

**Date**: 2026-02-26
**Feature**: 004-azure-ad-integrated-auth

## R1: Token Acquisition Library (azure-identity)

**Decision**: Use `azure-identity` with `DefaultAzureCredential`, excluding interactive browser credential.

**Rationale**: `DefaultAzureCredential` provides a credential chain that tries multiple non-interactive sources in order: environment variables → managed identity → Azure CLI → Azure PowerShell. The `exclude_interactive_browser_credential` parameter defaults to `True` already, satisfying FR-005 without extra configuration. Tenant targeting is supported via `get_token(scope, tenant_id=...)` since v1.12.0.

**Alternatives considered**:
- `msal` directly: Lower-level, requires manual credential source management. More work for the same result.
- `az` CLI subprocess: External tool dependency, slower, not always available. Rejected per FR-005.
- ODBC driver's built-in `Authentication=ActiveDirectoryIntegrated`: Causes Private Link DNS resolution failures on the target environment. This is the root problem being solved.

**Key API details**:
- `DefaultAzureCredential(exclude_interactive_browser_credential=True, exclude_visual_studio_code_credential=True)`
- `credential.get_token("https://database.windows.net/.default", tenant_id=optional_tenant)`
- Returns `AccessToken(token=str, expires_on=int)` (epoch seconds)
- Minimum version: `>=1.14.0`

## R2: Token Packing for pyodbc (SQL_COPT_SS_ACCESS_TOKEN)

**Decision**: Pack tokens as `struct.pack("<I", len(encoded)) + encoded` where `encoded = token.encode("utf-16-le")`.

**Rationale**: The ODBC Driver 18 expects a C struct at connection attribute 1256 with a 4-byte little-endian length prefix followed by the UTF-16LE encoded token string (no null terminator). pyodbc passes `bytes` values in `attrs_before` as `SQL_IS_POINTER` to `SQLSetConnectAttrW`.

**Alternatives considered**:
- Using `Authentication=ActiveDirectoryManagedIdentity` ODBC keyword: Only works for managed identity, not the general credential chain.
- ctypes struct: Unnecessary complexity; `struct.pack` achieves the same result.

**Key implementation detail**: When using token-based auth, the ODBC connection string must NOT include `UID`, `PWD`, or `Authentication` keywords — they conflict with `SQL_COPT_SS_ACCESS_TOKEN`.

## R3: SQLAlchemy Integration (creator function + pool behavior)

**Decision**: Use `create_engine(creator=callable)` with `pool_pre_ping=True` and `pool_recycle=3600`.

**Rationale**: The `creator` callable is invoked whenever SQLAlchemy's pool needs a new physical connection. Combined with `pool_pre_ping=True` (already the project default), stale connections are detected and discarded, triggering `creator` again with a fresh token. `pool_recycle=3600` aligns with the ~1-hour token lifetime. This means every new physical connection gets a fresh token — no separate token refresh logic needed.

**Alternatives considered**:
- `PoolEvents.checkout` event listener: More granular control over token expiry checking, but adds complexity. The `creator` + `pool_pre_ping` pattern is simpler and sufficient.
- Disabling pooling entirely (`NullPool`): Would work but sacrifices connection reuse within the token validity window.

**Key behavior**: `creator` is NOT called on every checkout — only when a new physical connection is needed. Existing pooled connections are reused until they fail `pool_pre_ping` or exceed `pool_recycle`.

## R4: Token Scope for Azure SQL

**Decision**: Use `https://database.windows.net/.default` as the token scope.

**Rationale**: This is the documented scope for Azure SQL Database, Azure SQL Managed Instance, and Azure Synapse Analytics. The `/.default` suffix is required — without it, token acquisition fails.

## R5: Dependency Impact Assessment

**Decision**: Add `azure-identity>=1.14.0` as a core dependency.

**Rationale**: Transitive dependencies are `azure-core`, `msal`, `msal-extensions`, `cryptography`, `PyJWT`, `requests`, and `typing-extensions`. Most of these are ubiquitous in Python environments. The `requests` library is the most significant addition but is extremely stable and well-maintained. The team uniformly targets Azure SQL, making this a justified core dependency per spec FR-008.

**Risk**: `cryptography` requires C extensions (pre-built wheels available for all major platforms). This is the only dependency that could cause installation friction, but it's one of the most widely-used Python packages.
