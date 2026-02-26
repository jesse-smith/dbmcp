# Feature Specification: Azure AD Integrated Authentication

> **STATUS: COMPLETE** | Merged: 2026-02-26 | Branch: `004-azure-ad-integrated-auth`

**Feature Branch**: `004-azure-ad-integrated-auth`
**Created**: 2026-02-26
**Status**: Complete
**Input**: User description: "Add ActiveDirectoryIntegrated authentication support using azure-identity's DefaultAzureCredential for token-based Azure AD auth. This adds a new AZURE_AD_INTEGRATED enum value to AuthenticationMethod, acquires tokens via azure-identity (not az CLI), and passes them to pyodbc via SQL_COPT_SS_ACCESS_TOKEN. azure-identity is a core dependency (not optional) since the team targets Azure SQL. The existing AZURE_AD (ActiveDirectoryPassword) method remains unchanged. Key considerations: token refresh for pooled connections (tokens expire ~1hr), the SQL_COPT_SS_ACCESS_TOKEN struct packing for pyodbc, and using SQLAlchemy's creator function to inject tokens at connection creation time."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect to Azure SQL with Integrated Auth (Priority: P1)

A team member wants to connect to an Azure SQL database (e.g., `stjude-edw.database.windows.net`) using their existing Azure AD identity without providing a username or password. The system authenticates using their current Azure credentials (e.g., cached from `az login`, managed identity, or environment variables) and establishes a working database connection.

**Why this priority**: This is the core capability. The team's primary database target is Azure SQL, and integrated auth eliminates credential management overhead while aligning with organizational security policies.

**Independent Test**: Can be fully tested by connecting to an Azure SQL database using the new auth method and executing a simple query to confirm the connection works.

**Acceptance Scenarios**:

1. **Given** a user has valid Azure AD credentials available (via any supported credential source), **When** they connect using the `azure_ad_integrated` authentication method without providing username or password, **Then** a database connection is established successfully.

2. **Given** a user has valid Azure AD credentials available, **When** they connect and execute a simple query (e.g., `SELECT 1`), **Then** the query returns results, confirming the connection is functional.

3. **Given** a user specifies the `azure_ad_integrated` method but also provides username/password, **Then** the system ignores the username/password and authenticates via the integrated credential chain.

---

### User Story 2 - Transparent Token Refresh for Long Sessions (Priority: P1)

A team member is working with an Azure SQL database over an extended session (longer than one hour). When the initial access token expires, new connections from the pool automatically acquire fresh tokens without the user needing to reconnect or take any action.

**Why this priority**: Azure AD tokens expire after approximately one hour. Without automatic refresh, every long session would break silently, requiring manual reconnection and disrupting workflows.

**Independent Test**: Can be tested by establishing a connection, waiting for the token to expire (or simulating expiry), and verifying that a subsequent query succeeds without manual intervention.

**Acceptance Scenarios**:

1. **Given** a user has an active connection using `azure_ad_integrated`, **When** the access token expires and a new connection is drawn from the pool, **Then** a fresh token is automatically acquired and the query succeeds.

2. **Given** a user has an active connection, **When** the underlying credential source is still valid but the token has expired, **Then** the system acquires a new token without user interaction.

---

### User Story 3 - Clear Error Messages for Auth Failures (Priority: P2)

A team member attempts to connect using `azure_ad_integrated` but has no valid Azure AD credentials available (not logged in, expired session, etc.). The system provides a clear, actionable error message explaining what went wrong and how to resolve it.

**Why this priority**: Authentication failures can be confusing. Clear error messaging reduces support burden and helps users self-resolve credential issues.

**Independent Test**: Can be tested by attempting to connect without valid Azure credentials and verifying the error message is informative.

**Acceptance Scenarios**:

1. **Given** a user has no Azure AD credentials available, **When** they attempt to connect using `azure_ad_integrated`, **Then** the system returns an error message explaining that no Azure AD credentials were found and suggesting remediation steps.

2. **Given** a user's Azure AD credentials have expired, **When** they attempt to connect, **Then** the error message indicates that credentials are expired and suggests re-authentication.

---

### Edge Cases

- What happens when the Azure SQL endpoint resolves through Private Link (e.g., inserts `privatelink` in the domain)?
  - Token-based auth bypasses the ODBC driver's internal DNS/auth flow entirely, so Private Link DNS resolution is handled normally by the OS network stack, not the driver's auth layer.
- What happens when multiple Azure AD identities are available (e.g., environment vars and az CLI)?
  - The credential chain follows a defined precedence order; the first successful credential source wins. This is standard and expected behavior.
- What happens when the user has Azure AD permissions to authenticate but lacks database-level permissions?
  - Token acquisition succeeds but the database query fails with a SQL Server permission error. This is a database authorization issue, not an authentication issue, and the database error message is passed through as-is.
- What happens when the system is running in an environment with no Azure AD capability (e.g., no managed identity, no CLI, no env vars)?
  - The credential chain exhausts all sources and raises a clear error before any connection attempt is made.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support a new `azure_ad_integrated` authentication method that authenticates using the caller's Azure AD identity without requiring username or password, with an optional tenant ID to target a specific Azure AD tenant (defaults to the credential chain's default tenant if omitted)
- **FR-002**: System MUST acquire access tokens scoped to the Azure SQL resource endpoint for database connectivity
- **FR-003**: System MUST pass acquired tokens to the database driver using the token-based connection attribute mechanism, bypassing the ODBC driver's built-in authentication keywords
- **FR-004**: System MUST automatically acquire fresh tokens for new connections from the pool when existing tokens have expired
- **FR-005**: System MUST NOT require the Azure CLI (`az`) to be installed; the token acquisition capability must support multiple non-interactive credential sources (environment variables, managed identity, CLI if available) but MUST NOT include interactive browser-based authentication
- **FR-006**: System MUST provide actionable error messages when token acquisition fails, including guidance on how to establish valid credentials
- **FR-007**: System MUST NOT modify the behavior of existing authentication methods (`sql`, `windows`, `azure_ad`)
- **FR-008**: The token acquisition capability MUST be a core (non-optional) dependency of the project

### Key Entities

- **AuthenticationMethod**: Existing enum representing supported auth methods. Extended with a new `azure_ad_integrated` value.
- **Connection**: Existing connection metadata model. No structural changes needed; the `username` field remains optional (will be None for integrated auth).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can connect to Azure SQL databases using `azure_ad_integrated` without providing any username or password
- **SC-002**: Connections remain functional across token expiration boundaries (sessions longer than 1 hour) without user intervention
- **SC-003**: All existing authentication methods (`sql`, `windows`, `azure_ad`) continue to function identically with zero regressions
- **SC-004**: Authentication failures produce error messages that include a suggested remediation action
- **SC-005**: The system successfully authenticates in at least two distinct credential environments (e.g., Azure CLI-based and environment variable-based)

## Clarifications

### Session 2026-02-26

- Q: Should the system allow interactive browser authentication as a fallback, or restrict to non-interactive credential sources only? → A: Non-interactive only; exclude interactive browser from the credential chain (incompatible with MCP server context).
- Q: Should the connection API accept an optional tenant ID parameter to target a specific Azure AD tenant? → A: Yes, optional `tenant_id` parameter; if omitted, uses the default tenant from the credential chain.

## Assumptions

- The team uniformly targets Azure SQL databases, making the token acquisition library a justified core dependency
- The credential chain uses non-interactive sources only (environment vars > managed identity > CLI); interactive browser fallback is excluded as incompatible with MCP server execution context
- Token expiration is approximately 1 hour; acquiring a fresh token per new pooled connection is acceptable overhead
- The ODBC Driver 18 for SQL Server (already a project dependency) supports token-based authentication via connection attributes
- Private Link DNS resolution issues are specific to the ODBC driver's built-in `ActiveDirectoryIntegrated` auth flow and do not affect token-based auth
