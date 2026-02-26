# Implementation Plan: Azure AD Integrated Authentication

**Branch**: `004-azure-ad-integrated-auth` | **Date**: 2026-02-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-azure-ad-integrated-auth/spec.md`

## Summary

Add `azure_ad_integrated` as a new authentication method that uses `azure-identity`'s `DefaultAzureCredential` to acquire Azure AD tokens and pass them to pyodbc via `SQL_COPT_SS_ACCESS_TOKEN`. This bypasses the ODBC driver's built-in Azure AD auth flow (which fails with Private Link DNS resolution) and provides transparent token refresh for long-running sessions via SQLAlchemy's `creator` function pattern.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: SQLAlchemy >=2.0.0, pyodbc >=5.0.0, azure-identity >=1.14.0 (new), mcp[cli] >=1.0.0 (existing)
**Storage**: N/A (in-memory connection management only)
**Testing**: pytest (existing)
**Target Platform**: macOS/Linux (developer workstations + Azure-hosted environments)
**Project Type**: MCP server (CLI tool)
**Performance Goals**: Token acquisition <5s (network-dependent); no added latency for pooled connection reuse
**Constraints**: Non-interactive credential sources only (no browser popups); ODBC Driver 18 required
**Scale/Scope**: Team of developers targeting Azure SQL; single new auth method + ~1 new module

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First (YAGNI) | **Pass** | Feature addresses a concrete, immediate requirement (team can't connect via built-in AD auth). One new module, one new enum value, minimal abstraction. |
| II. DRY | **Pass** | Token packing logic exists in one place (`azure_auth.py`). ODBC string building extends existing method. |
| III. Test-First Development | **Pass** | Unit tests for token packing, credential validation, ODBC string generation. Integration test for live Azure SQL connection. |
| IV. Explicit Error Handling | **Pass** | `CredentialUnavailableError` from azure-identity is caught and translated to actionable user messages. Token packing errors fail fast. |
| V. Performance by Design | **Pass** | Fresh token only on new physical connection (not every checkout). `pool_pre_ping` + `pool_recycle` handle staleness. No I/O in loops. |
| VI. Code Quality Through Clarity | **Pass** | `AzureTokenProvider` has a single responsibility. `pack_token_for_pyodbc` is a small pure function. |
| VII. Minimal Dependencies | **Pass** | `azure-identity` is the standard Microsoft-maintained library for this purpose. Not achievable in <50 lines. Well-maintained with active security response. Core dependency justified by team requirement. |

**Post-Phase 1 re-check**: All gates still pass. No new abstractions beyond `AzureTokenProvider`. No speculative features.

## Project Structure

### Documentation (this feature)

```text
specs/004-azure-ad-integrated-auth/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── connect-database-tool.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (not yet created)
```

### Source Code (repository root)

```text
src/
├── db/
│   ├── connection.py     # Modified: add tenant_id param, creator function for azure_ad_integrated
│   └── azure_auth.py     # New: AzureTokenProvider class + token packing
├── models/
│   └── schema.py         # Modified: add AZURE_AD_INTEGRATED enum value
└── mcp_server/
    └── server.py         # Modified: add tenant_id param to connect_database tool

tests/
└── unit/
    ├── test_connection.py   # Modified: add azure_ad_integrated tests
    └── test_azure_auth.py   # New: token provider + packing tests
```

**Structure Decision**: Single project structure (existing). One new file (`azure_auth.py`) in `src/db/` alongside `connection.py`. One new test file (`test_azure_auth.py`). No new directories needed.
