# Tasks: Azure AD Integrated Authentication

**Input**: Design documents from `/specs/004-azure-ad-integrated-auth/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/connect-database-tool.md, quickstart.md

**Tests**: TDD approach per project CLAUDE.md — tests are written first and must fail before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add dependency and extend enum — prerequisites for all stories

- [ ] T001 Add `azure-identity>=1.14.0` to core dependencies in pyproject.toml
- [ ] T002 Add `AZURE_AD_INTEGRATED = "azure_ad_integrated"` enum value to `AuthenticationMethod` in src/models/schema.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the token provider module that all user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational Phase

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T003 Write unit tests for `pack_token_for_pyodbc` (correct struct packing: 4-byte LE length prefix + UTF-16LE encoded token) in tests/unit/test_azure_auth.py
- [ ] T004 [P] Write unit tests for `AzureTokenProvider.__init__` (credential creation with/without tenant_id, exclude_interactive_browser_credential=True, exclude_visual_studio_code_credential=True) in tests/unit/test_azure_auth.py
- [ ] T005 [P] Write unit tests for `AzureTokenProvider.get_token` (returns token string, calls credential.get_token with correct scope `https://database.windows.net/.default`) in tests/unit/test_azure_auth.py

### Implementation for Foundational Phase

- [ ] T006 Create `AzureTokenProvider` class in src/db/azure_auth.py: `__init__(tenant_id: str | None = None)` creates `DefaultAzureCredential` with non-interactive sources only; `get_token() -> str` acquires token scoped to `https://database.windows.net/.default`; `pack_token_for_pyodbc(token: str) -> bytes` packs token as `struct.pack("<I", len(encoded)) + encoded` where `encoded = token.encode("utf-16-le")`
- [ ] T007 Verify foundational tests pass (run `pytest tests/unit/test_azure_auth.py`)

**Checkpoint**: Token provider module ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Connect to Azure SQL with Integrated Auth (Priority: P1) 🎯 MVP

**Goal**: Users can connect to Azure SQL using `azure_ad_integrated` without username/password

**Independent Test**: Connect to an Azure SQL database using the new auth method and execute `SELECT 1`

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T008 [US1] Write unit tests in tests/unit/test_connection.py that: (a) `azure_ad_integrated` auth method does NOT require username/password validation, and (b) providing username/password with `azure_ad_integrated` is silently ignored (no error raised, values not used) per spec acceptance scenario 1.3
- [ ] T009 [P] [US1] Write unit test for `_build_odbc_connection_string` with `azure_ad_integrated`: string must NOT contain `UID`, `PWD`, or `Authentication` keywords; must contain Driver, Server, Database, TrustServerCertificate, Connection Timeout in tests/unit/test_connection.py
- [ ] T010 [P] [US1] Write unit test that `connect()` with `azure_ad_integrated` uses `create_engine(creator=...)` pattern instead of URL-based connection in tests/unit/test_connection.py
- [ ] T011 [P] [US1] Write unit test that connection ID hash uses `'azure_ad'` (not username) when auth method is `azure_ad_integrated` in tests/unit/test_connection.py. Design note: current code falls through to `'windows'` when username is None; `'azure_ad'` disambiguates integrated auth connections in the hash.

### Implementation for User Story 1

- [ ] T012 [US1] Update `_build_odbc_connection_string` in src/db/connection.py to handle `AZURE_AD_INTEGRATED`: emit only Driver, Server, Database, TrustServerCertificate, Connection Timeout (no UID/PWD/Authentication)
- [ ] T013 [US1] Add `tenant_id: str | None = None` parameter to `ConnectionManager.connect()` in src/db/connection.py. Note: this brings `connect()` to 9 params, exceeding the constitution's 5-param complexity budget. Justified: all params are direct ODBC/auth concerns with no natural grouping that wouldn't be a premature abstraction (Principle I). Pre-existing condition (already at 8). Document in code review.
- [ ] T014 [US1] Update `connect()` in src/db/connection.py: when auth method is `azure_ad_integrated`, create `AzureTokenProvider`, build a `creator` callable that acquires a fresh token via provider, packs it, and returns a `pyodbc.connect()` with `attrs_before={1256: packed_token}`; pass `creator` to `create_engine` instead of URL
- [ ] T015 [US1] Update connection ID hash in `connect()` in src/db/connection.py to use `'azure_ad'` instead of username for `azure_ad_integrated` auth (prevents collision with Windows auth's `'windows'` fallback when username is None)
- [ ] T016 [US1] Add `tenant_id: str | None = None` parameter to `connect_database` tool in src/mcp_server/server.py, pass through to `conn_manager.connect()`
- [ ] T017 [US1] Update invalid auth method error message in src/mcp_server/server.py to include `'azure_ad_integrated'` in the list of valid methods
- [ ] T018 [US1] Verify User Story 1 tests pass (run `pytest tests/unit/test_connection.py tests/unit/test_azure_auth.py`)

**Checkpoint**: Users can connect to Azure SQL using `azure_ad_integrated` — core capability complete

---

## Phase 4: User Story 2 — Transparent Token Refresh for Long Sessions (Priority: P1)

**Goal**: New connections from the pool automatically acquire fresh tokens when previous tokens expire

**Independent Test**: Verify that the `creator` callable acquires a fresh token on each invocation (simulating pool creating new physical connections after token expiry)

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T019 [US2] Write unit test that the `creator` callable calls `AzureTokenProvider.get_token()` on every invocation (not cached) in tests/unit/test_connection.py
- [ ] T020 [P] [US2] Write unit test that `pool_pre_ping=True` and `pool_recycle=3600` are set on the engine created for `azure_ad_integrated` connections in tests/unit/test_connection.py

### Implementation for User Story 2

- [ ] T021 [US2] Code review + validate that the `creator` function from T014 calls `provider.get_token()` fresh on each invocation (no token caching in the creator — `azure-identity` handles its own token cache internally). No new code expected; this validates the US1 implementation satisfies US2's refresh requirement.
- [ ] T022 [US2] Code review + validate that `pool_pre_ping` and `pool_recycle` from `PoolConfig` are applied to the `azure_ad_integrated` engine in src/db/connection.py. No new code expected; this confirms existing pool defaults cover token expiry.
- [ ] T023 [US2] Verify User Story 2 tests pass (run `pytest tests/unit/test_connection.py -k "refresh or pool or creator"`)

**Checkpoint**: Token refresh is automatic — long sessions work without manual intervention

---

## Phase 5: User Story 3 — Clear Error Messages for Auth Failures (Priority: P2)

**Goal**: Authentication failures produce actionable error messages with remediation guidance

**Independent Test**: Attempt connection with mocked `CredentialUnavailableError` and verify error message content

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T024 [US3] Write unit test that `CredentialUnavailableError` from `azure-identity` is caught and translated to an actionable message mentioning `az login` and environment variable setup in tests/unit/test_azure_auth.py
- [ ] T025 [P] [US3] Write unit test that `ClientAuthenticationError` (expired credentials) produces a message indicating credentials are expired and suggesting re-authentication in tests/unit/test_azure_auth.py
- [ ] T026 [P] [US3] Write unit test that `connect()` propagates the actionable error message from `AzureTokenProvider` as a `ConnectionError` in tests/unit/test_connection.py

### Implementation for User Story 3

- [ ] T027 [US3] Add error handling to `AzureTokenProvider.get_token()` in src/db/azure_auth.py: catch `CredentialUnavailableError` → raise with message "Azure AD authentication failed: No credential sources available. Run 'az login' or set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID environment variables."
- [ ] T028 [US3] Add error handling for `ClientAuthenticationError` in src/db/azure_auth.py → raise with message indicating expired credentials and suggesting re-authentication
- [ ] T029 [US3] Ensure `connect()` in src/db/connection.py catches token provider errors and wraps them in `ConnectionError` with the actionable message preserved
- [ ] T030 [US3] Verify User Story 3 tests pass (run `pytest tests/unit/test_azure_auth.py tests/unit/test_connection.py -k "error or fail"`)

**Checkpoint**: All auth failures produce clear, actionable error messages

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, regression checks, and cleanup

- [ ] T031 Run full test suite (`pytest tests/`) and verify zero regressions on existing auth methods (sql, windows, azure_ad)
- [ ] T032 Run `ruff check src/ tests/` and fix any lint warnings
- [ ] T033 **[Integration test required]** Validate quickstart.md scenarios against a live Azure SQL instance. Must verify SC-005: successful authentication in at least two distinct credential environments (e.g., Azure CLI-based and environment variable-based). Also verify token acquisition completes within the 5s performance target from plan.md (network-dependent; log timing for review).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (enum value + dependency must exist)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (`AzureTokenProvider` must exist)
- **User Story 2 (Phase 4)**: Depends on Phase 3 (creator function must exist to verify refresh behavior)
- **User Story 3 (Phase 5)**: Depends on Phase 2 (`AzureTokenProvider` must exist for error handling); can run in parallel with US1/US2 if desired
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational. This is the core MVP.
- **User Story 2 (P1)**: Logically depends on US1 (the creator function is built in US1; US2 verifies its refresh behavior). Can be validated during US1 implementation.
- **User Story 3 (P2)**: Depends on Foundational only. Can be implemented in parallel with US1/US2.

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models/providers before connection logic
- Connection logic before MCP server changes
- Core implementation before integration
- Story verification before moving to next priority

### Parallel Opportunities

- T004 and T005 can run in parallel (different test concerns, same file but independent sections)
- T009, T010, T011 can run in parallel (different test cases in test_connection.py)
- T024, T025, T026 can run in parallel (different error scenarios)
- User Story 3 (Phase 5) can run in parallel with User Stories 1-2 (Phases 3-4) since US3 only depends on Phase 2

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (they test different aspects):
Task: "Unit test for ODBC string with azure_ad_integrated in tests/unit/test_connection.py"
Task: "Unit test for creator pattern in tests/unit/test_connection.py"
Task: "Unit test for connection ID hash in tests/unit/test_connection.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (add dependency + enum)
2. Complete Phase 2: Foundational (token provider with tests)
3. Complete Phase 3: User Story 1 (connect with integrated auth)
4. **STOP and VALIDATE**: Test against live Azure SQL if available
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Token provider ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Verify token refresh behavior
4. Add User Story 3 → Test error scenarios → Deploy/Demo
5. Polish → Full regression + lint pass

---

## Notes

- [P] tasks = different files or independent sections, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each phase or logical group
- Stop at any checkpoint to validate story independently
- Token caching is handled internally by `azure-identity` — do NOT add a separate cache layer
- The `creator` function pattern inherently provides token refresh (research R3)
- ODBC connection string for `azure_ad_integrated` MUST NOT include UID/PWD/Authentication (research R2)
