# Project Research Summary

**Project:** TOON format serialization migration for dbmcp MCP server
**Domain:** Serialization format migration (JSON to TOON) for LLM-optimized responses
**Researched:** 2026-03-04
**Confidence:** HIGH

## Executive Summary

This project migrates an existing MCP server from JSON to TOON (Tabular Object Oriented Notation) serialization for all tool responses. TOON is specifically designed to reduce token consumption for LLM clients by using tabular encoding for uniform arrays, achieving 30-60% token savings on database query results compared to JSON. The migration is architecturally simple—a mechanical replacement of `json.dumps()` with `toon_format.encode()` at 41 call sites across 9 MCP tools—but has high coordination overhead due to pervasive test suite updates (64 deserialization sites) and mandatory docstring rewrites (FastMCP sends docstrings to LLM clients as API descriptions).

The recommended approach is atomic migration: all 9 tools in a single phase with simultaneous test infrastructure updates and docstring rewrites. The primary risk is silent data corruption from TOON's type normalizer (Enums and dataclasses become null if not pre-serialized to primitives), mitigated by strict adherence to the pattern: always pass plain dicts/lists/primitives to `encode()`. Secondary risks include test brittleness if assertions compare raw strings instead of decoded structures, and dependency volatility since `toon-format` is at 0.9.0-beta with no 1.0 release in 4 months.

The migration delivers immediate token savings (most impactful for high-volume tools like `execute_query`, `get_sample_data`, `list_tables`) without changing response structure or MCP protocol. Post-migration, a docstring-schema staleness test prevents future drift between documentation and actual output format. This is a low-risk, high-value refactor with clear success criteria: all tests green, docstrings accurate, token savings validated.

## Key Findings

### Recommended Stack

The stack is minimal: add one dependency (`toon-format>=0.9.0b1`) to the existing Python 3.11+ project with FastMCP, SQLAlchemy, and pyodbc. No supporting libraries are required at runtime; `tiktoken` is optionally useful for development-time benchmarking to measure actual token savings per tool.

**Core technologies:**
- **toon-format (>=0.9.0b1):** TOON serialization via `toon_format.encode()` — only official Python implementation; single-function API accepting any JSON-serializable value, directly replaces `json.dumps()`. Pre-release but functional; 0.1.0 is a namespace stub with no implementation, so version pinning to beta is mandatory.
- **Python (>=3.11, existing):** Runtime — already pinned; toon-format supports >=3.10, no conflict.
- **FastMCP (existing):** MCP framework — unchanged; tools still return strings, transport agnostic to serialization format.

**Key constraint:** `toon_format.encode()` has no `default=str` parameter. Tools currently using `json.dumps(response, default=str)` must pre-serialize datetime/Decimal objects to strings before encoding. The `default=str` safety net disappears with TOON.

**Version pinning strategy:** Use `toon-format>=0.9.0b1,<1.0.0` to avoid surprise breaking changes when 1.0 ships, or pin exactly to `==0.9.0b1` for maximum stability. Library has been stalled at beta since Nov 2025 (4 months with no subsequent release), suggesting slow development cadence but also API stability.

### Expected Features

Research identified 6 table-stakes features, 5 differentiators, and 5 explicit anti-features (format negotiation, auto-generated docstrings, Pydantic migration, custom encoder, streaming).

**Must have (table stakes):**
- Replace `json.dumps()` with `toon_format.encode()` at all 41 call sites across 9 tools — the core deliverable
- Update all 64 test assertions from `json.loads()` to `toon_format.decode()` — without this, test suite explodes immediately
- Update all 9 tool docstrings to show TOON format instead of JSON — FastMCP sends docstrings to LLM clients; stale docs break consumer expectations
- Handle error responses correctly — every tool has `{"status": "error", ...}` paths; must encode cleanly
- Preserve response structure (field names, types, nesting) — PROJECT.md constraint; only serialization format changes

**Should have (competitive):**
- Docstring-schema staleness test — catches drift automatically; PROJECT.md core requirement; prevents future rot
- Tabular encoding for list-heavy responses — TOON's biggest token savings come from arrays of uniform objects; tools like `list_tables`, `execute_query`, `get_sample_data` automatically benefit with no code changes
- Token savings measurement — quantifies actual 30-60% savings claim with `toon_format.estimate_savings()`; validates business case

**Defer (v2+):**
- Response restructuring for better tabular optimization — e.g., flattening conditional fields in analysis tools; only if measurement shows significant opportunity
- TOON encode options tuning (delimiter, indent, lengthMarker) — defaults are LLM-optimized; only change if evidence suggests otherwise

**Response shape analysis:** 9 tools break down as follows: 5 return uniform arrays (high tabular benefit: `list_schemas`, `list_tables`, `get_sample_data`, `execute_query`, `find_pk_candidates`), 1 returns conditionally-uniform arrays (`find_fk_candidates` — tabular when `include_overlap=False`), 2 return non-uniform arrays (`get_column_info`, `get_table_schema` — falls back to expanded list), 1 returns flat dict (`connect_database` — minimal savings). Expected savings: 50% for high-volume tools, 30-40% for mixed, 20% for flat.

### Architecture Approach

The migration is a leaf-node serialization swap with zero changes to data models, service layer, or database interactions. The architectural insight: every tool already constructs a plain Python dict, then calls `json.dumps()` as the final step. The dict construction is untouched; only the final serialization call changes.

**Major components:**
1. **Tool functions (schema_tools, query_tools, analysis_tools)** — Orchestrate business logic, build response dicts, serialize to string. CHANGE: swap `json.dumps()` for `toon_format.encode()` at return statements.
2. **Response dict construction** — Each tool builds `{"status": "success", ...data...}` from service layer results. NO CHANGE: dict structure stays identical.
3. **Docstrings** — FastMCP reads these verbatim as tool descriptions sent to LLM clients. CHANGE: rewrite `Returns:` sections to document TOON format with TOON examples, not JSON curly braces.
4. **Staleness test (NEW)** — Validates docstrings match actual response schemas. ADDITION: new test file in `tests/compliance/test_docstring_staleness.py`.
5. **Test assertions** — 64 `json.loads()` calls across 6 test files parse tool return values. CHANGE: replace with `toon_format.decode()` or test against dicts before serialization.

**Key architectural decision rejected:** No serialization abstraction layer. A wrapper function like `serialize_response(dict, format="toon")` would be over-engineering for a one-liner substitution when PROJECT.md explicitly rules out format negotiation. Direct `toon_format.encode()` calls at each site are clearer and easier to review.

**Build order:** (1) Add dependency, (2) Swap serialization in all tools atomically, (3) Update docstrings in same commit, (4) Update test assertions, (5) Add staleness test. Rationale: atomic tool migration prevents mixed JSON/TOON state; docstrings must be updated simultaneously or LLM clients get wrong format descriptions; tests updated after tools to avoid mixed expectations.

### Critical Pitfalls

Research identified 6 critical pitfalls with detailed prevention strategies:

1. **Enum and Dataclass Silent Null Coercion** — TOON's normalizer converts unsupported types (Python Enums, dataclasses) to `None` with only a warning log, no error. If a tool accidentally passes a raw `SamplingMethod.TOP` or raw dataclass to `encode()` instead of `.value`/`.to_dict()`, the value silently becomes null in output. **Prevention:** Keep existing pattern: always serialize to plain dicts/lists/primitives BEFORE calling `encode()`. Write a unit test that passes raw Enum/dataclass and asserts output does NOT contain null. This is the highest-risk pitfall because JSON would throw `TypeError` on an Enum; TOON silently corrupts it.

2. **Test Suite Deserialization Breakage (64 json.loads Calls)** — Integration tests have 64 `json.loads()` calls across 6 files that parse tool responses. After TOON migration, every one throws `JSONDecodeError`, creating a wall of failures that obscures real bugs. **Prevention:** Introduce a test helper `parse_tool_response(str) -> dict` that encapsulates deserialization. Flip this one function from `json.loads` to `toon_format.decode` during migration. Migrate test infrastructure BEFORE or IN PARALLEL with tool changes, not after.

3. **Docstring-Schema Drift After Format Change** — All 9 tools have detailed JSON examples in docstrings (curly braces, quoted keys). FastMCP sends these to LLM clients. After TOON encoding, docstrings still describe JSON but output is TOON, causing LLM confusion. **Prevention:** Update docstrings in SAME commit as encoder swap for each tool. Implement staleness test early to catch mismatches. TOON docstrings must show TOON format examples, not JSON.

4. **Pre-Release Library Dependency Risk** — `toon-format` is at 0.9.0-beta.1 with "API may change before 1.0.0" warning. The `encode()` signature or behavior could break on upgrade. **Prevention:** Pin exact version `==0.9.0b1` in `pyproject.toml`. Consider a thin wrapper module so API changes update one file, not 9 tool files. Write integration tests with representative data (nested dicts, lists of dicts, None values) to catch behavioral changes.

5. **Partial Migration Leaves Inconsistent Client Experience** — If tools migrate incrementally over multiple PRs, LLM clients see mixed JSON/TOON responses, causing parse failures. MCP has no per-tool format negotiation. **Prevention:** Migrate all 9 tools in a single phase/PR. Never deploy a state where some tools return JSON and others return TOON.

6. **NaN/Infinity Float Normalization Changes Semantics** — TOON normalizes `float('nan')` and `float('inf')` to `None` (null). JSON raises `ValueError` by default. SQL Server can return NaN for edge cases like `STDEV` of single-row column; analysis tools compute `std_dev`, `mean_value` which could hit this. **Prevention:** Add explicit NaN/Infinity handling BEFORE encoding: `None if math.isnan(v) or math.isinf(v) else v`. Document this normalization so future developers understand.

## Implications for Roadmap

Based on research, recommended single-phase atomic migration with optional post-launch validation phase:

### Phase 1: Atomic TOON Migration
**Rationale:** The migration is a mechanical substitution (41 `json.dumps` → `toon_format.encode` call sites) with tight interdependencies: tools, tests, and docstrings must change together to avoid mixed-format state (Pitfall 5) or stale documentation (Pitfall 3). Splitting across multiple phases creates client confusion and doubles testing surface. Architecture analysis confirmed all 9 tools follow identical patterns (build dict → serialize), making batch migration feasible.

**Delivers:** All 9 MCP tools return TOON-encoded strings; all 64 test assertions parse TOON; all docstrings document TOON format; zero regression in response structure or functionality.

**Addresses features:**
- Replace `json.dumps()` with `toon_format.encode()` (41 sites)
- Update test assertions from `json.loads()` to `toon_format.decode()` (64 sites)
- Update tool docstrings for TOON format (9 tools)
- Handle error responses correctly (verified)
- Preserve response structure (enforced)

**Avoids pitfalls:**
- Partial migration inconsistency (atomic scope)
- Test suite breakage (helper refactor first)
- Docstring drift (simultaneous update)
- Enum/dataclass null coercion (explicit pre-serialization)
- NaN/Infinity normalization (explicit handling in analysis tools)
- Pre-release dependency risk (exact version pinning)

**Sub-steps:**
1. Add `toon-format==0.9.0b1` dependency
2. Introduce test helper `parse_tool_response()` (still using JSON, green tests)
3. Swap all 9 tools from `json.dumps()` to `toon_format.encode()` in one commit
4. Update all 9 tool docstrings to show TOON examples in same commit
5. Flip test helper from `json.loads` to `toon_format.decode` (green tests)
6. Verify enum/dataclass pre-serialization with unit test

**Success criteria:**
- All 385 existing tests pass
- No JSON-formatted examples remain in docstrings (`git grep "{\".*\":" | grep Returns` returns empty)
- No `json.dumps` calls remain in tool modules
- `parse_tool_response()` encapsulates all deserialization

### Phase 2: Post-Migration Validation (Optional)
**Rationale:** After Phase 1 is deployed, validate token savings claims and establish staleness test to prevent future drift. These are value-add features, not migration blockers. Docstring staleness test is a PROJECT.md requirement but can be implemented after format migration is verified working.

**Delivers:** Quantified token savings report; automated staleness test in CI preventing docstring-schema drift.

**Addresses features:**
- Docstring-schema staleness test (PROJECT.md requirement)
- Token savings measurement (validates business case)

**Uses stack elements:**
- `tiktoken` (optional dev dependency) for benchmarking
- `toon_format.estimate_savings()` utility

**Implements architecture:**
- Staleness test component (new `tests/compliance/test_docstring_staleness.py`)
- Schema-from-mock-response approach (reuses existing test fixtures)

**Sub-steps:**
1. Implement staleness test: extract field names from docstrings, compare against actual tool response dicts
2. Run token savings benchmark against existing test fixtures for all 9 tools
3. Document savings in migration report (PR description or internal doc)

**Success criteria:**
- Staleness test catches intentional schema/docstring mismatch (validation test)
- Token savings report confirms 30-60% reduction for high-volume tools
- CI runs staleness test on every commit

### Phase Ordering Rationale

- **Why atomic migration (not incremental):** MCP clients expect consistent format across all tools from the same server. Partial migration creates parse failures for LLMs. The code change is mechanical (41 one-liner substitutions), making batch feasible. Architecture research confirmed no tool-specific complications.

- **Why test helper before tool changes:** 64 `json.loads()` call sites across 6 test files would all break simultaneously if tools migrate first. A helper function allows test infrastructure to change once, then tools migrate without breaking tests. This sequence reduces coordination risk.

- **Why docstrings in same commit as tools:** FastMCP reads docstrings at import time and sends them to LLM clients. A tool returning TOON with a JSON-formatted docstring breaks client expectations immediately. Docstrings are part of the API contract, not documentation cleanup.

- **Why staleness test in Phase 2:** It's a guard rail for future changes, not a migration requirement. Phase 1 can ship without it as long as docstrings are manually verified. Adding it immediately after migration locks in correctness going forward.

- **How this avoids stack pitfalls:** Exact version pinning (0.9.0b1) prevents beta API breakage. Test helper decouples tests from TOON API changes. Explicit enum/dataclass serialization before `encode()` prevents silent null coercion. NaN/Infinity handling in analysis tools prevents silent data corruption.

### Research Flags

**Phase 1: No additional research needed.** Standard patterns:
- Serialization swap: well-documented in STACK.md; `encode()` is a one-function API
- Test refactoring: standard helper pattern
- Docstring updates: tedious but straightforward prose rewrite
- All tools inspected; no edge cases requiring deeper research

**Phase 2: No additional research needed.** Standard patterns:
- Staleness test: pattern documented in ARCHITECTURE.md (schema-from-mock-response)
- Token savings measurement: library-provided utility (`estimate_savings()`)

**Future consideration:** If Phase 2 token measurements reveal significantly lower savings than expected for analysis tools (due to non-uniform arrays breaking tabular encoding), consider Phase 3 to restructure responses for better tabular fit. But this is speculative; defer until data is available.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core API (`encode()`) is simple and well-documented, but library is pre-1.0 beta (0.9.0b1) with no release in 4 months. Exact version pinning mitigates risk. Confidence would be HIGH if library were stable. |
| Features | HIGH | All 9 tools inspected; 41 `json.dumps` call sites cataloged; 64 test assertions counted; docstring format verified. Feature set is well-scoped with clear table stakes vs. differentiators. |
| Architecture | HIGH | Codebase analysis confirmed leaf-node serialization pattern; no abstraction layer needed; build order dependencies mapped; staleness test approach validated against existing 385-test suite. |
| Pitfalls | HIGH | 6 critical pitfalls identified with specific prevention strategies; each validated against actual codebase patterns (e.g., `default=str` usage in `get_column_info`, enum usage in tool params); recovery costs estimated. |

**Overall confidence:** HIGH

Research is comprehensive for the migration scope. The one MEDIUM area (stack) reflects external dependency risk (beta library), not knowledge gaps. All other areas have HIGH confidence based on primary source analysis (codebase inspection, library source code, official docs).

### Gaps to Address

**Gap 1: Actual TOON output quality for non-uniform arrays**
- **What's unknown:** Analysis tools (`get_column_info`, `get_table_schema`) return objects with conditional fields (e.g., `numeric_stats` only present for numeric columns). Research predicts TOON falls back to expanded list format, but actual token savings need measurement.
- **Handle by:** Phase 2 token measurements will quantify this. If savings are <20% for these tools, document as known limitation; if >40%, no action needed; if 20-40%, consider Phase 3 for response restructuring (always include all fields as null to enable tabular).

**Gap 2: TOON library behavior with datetime objects**
- **What's unknown:** STACK.md says "TOON normalizes datetime to ISO 8601 per spec," but toon-format is encode-only for JSON-serializable values. Unclear if `datetime` objects are accepted directly or must be pre-converted.
- **Handle by:** Phase 1 implementation will test with real `datetime.datetime.now()`. If `encode()` accepts it, remove `.isoformat()` calls. If not, keep existing pattern (pre-convert to string before encoding). Low-risk because current code already pre-converts.

**Gap 3: Staleness test validation strategy**
- **What's unknown:** How to parse TOON format descriptions from docstrings to extract expected schema. Docstrings are prose, not machine-readable.
- **Handle by:** Phase 2 staleness test will use manual schema declarations (Python dicts mapping tool name → expected fields) rather than parsing docstrings. This is intentional—schema declarations are the cross-check against both code and docstrings. Approach validated in ARCHITECTURE.md Pattern 3.

**None of these gaps block Phase 1.** They are validation or optimization questions answered during implementation or post-launch measurement.

## Sources

### Primary (HIGH confidence)
- **Codebase inspection** — All 9 tools, 3 tool modules, 6 test files manually inspected; call site counts verified with `git grep`
- **PROJECT.md** — Project constraints, hard decisions (no format negotiation, no auto-generated docstrings, staleness test requirement)
- **toon-format library source** — GitHub toon-format/toon-python: `normalize.py` enum/dataclass behavior, `encode()` signature, `EncodeOptions` fields
- **PyPI toon-format page** — Version history (0.1.0 stub, 0.9.0b1 beta), Python compatibility (>=3.10), beta warning

### Secondary (MEDIUM confidence)
- **TOON specification v3.0 (Working Draft)** — GitHub toon-format/spec: tabular format for uniform arrays, indentation for nesting, 30-60% token savings claim
- **toon-python README** — API examples, `estimate_savings()` utility, `compare_formats()` benchmarking

### Tertiary (LOW confidence)
- None — all findings based on primary sources (codebase, library source, official docs)

---
*Research completed: 2026-03-04*
*Ready for roadmap: yes*
