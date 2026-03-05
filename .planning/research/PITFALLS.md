# Pitfalls Research

**Domain:** Serialization format migration (JSON to TOON) in MCP server responses
**Researched:** 2026-03-04
**Confidence:** HIGH (based on codebase inspection + TOON library source analysis)

## Critical Pitfalls

### Pitfall 1: Enum and Dataclass Silent Null Coercion

**What goes wrong:**
TOON's `normalize.py` converts unsupported types to `None` with only a warning log. Python `Enum` values (like `SamplingMethod.TOP`, `TableType.TABLE`, `QueryType.SELECT`) and dataclass instances are NOT explicitly handled by the normalizer. If any tool response passes a raw enum or dataclass object to `toon_format.encode()` instead of its `.value` or `.to_dict()` form, the value silently becomes `null` in the output. The LLM receives corrupted data with no error raised.

**Why it happens:**
The current code already calls `.value` on enums and `.to_dict()` on dataclasses before passing to `json.dumps()`. But during refactoring, a developer might think "TOON handles Python types like JSON does" and pass richer objects directly, expecting automatic serialization. JSON would throw `TypeError` on an enum; TOON silently nullifies it. The safety net disappears.

**How to avoid:**
1. Keep the existing pattern: always serialize to plain dicts/lists/primitives BEFORE calling `encode()`. TOON's `encode()` should receive the same dict that `json.dumps()` currently receives.
2. Write a unit test that passes a raw `StrEnum` member and a raw dataclass to `encode()` and asserts the output does NOT contain `null` where a value should be. If it does, the test catches the normalization trap.
3. Consider a thin wrapper: `def toon_encode(data): return toon_format.encode(data)` that can later add validation if needed.

**Warning signs:**
- Any tool response showing `null` where a string or object was expected
- Warnings in logs: "Unsupported type ... converting to null"
- Tests that check for specific field values suddenly passing with `None`

**Phase to address:**
Phase 1 (initial TOON integration). This must be understood before writing any `encode()` call. The architectural decision is: TOON replaces `json.dumps()` at the serialization boundary only, not the data preparation layer.

---

### Pitfall 2: Test Suite Deserialization Breakage (64 json.loads Calls)

**What goes wrong:**
The integration test suite has 64 `json.loads()` calls across 6 test files that parse tool return values. After switching to TOON output, every one of these will throw `json.JSONDecodeError` because TOON is not valid JSON. This is not one test file; it is pervasive. A naive "swap encode and run tests" approach results in a wall of failures that obscures any real bugs introduced during migration.

**Why it happens:**
Tests treat the serialization format as an implicit contract. They call the MCP tool function, get back a string, and immediately `json.loads()` it to inspect fields. There is no abstraction layer between "tool returned a string" and "parse the string into a dict."

**How to avoid:**
1. Create a test helper like `parse_tool_response(result_str: str) -> dict` that encapsulates deserialization. During migration, flip this one function from `json.loads` to `toon_format.decode`.
2. Migrate tests BEFORE or IN PARALLEL with the tool changes, not after. Specifically: introduce the helper on the JSON codebase (green tests), then switch tools to TOON and the helper to `decode()` simultaneously.
3. Do NOT try to make tools return both JSON and TOON -- that doubles the testing surface for no benefit.

**Warning signs:**
- More than 10 test failures after changing a single tool's serialization
- Test failures that are all `JSONDecodeError` rather than assertion failures (means you changed format but not test infrastructure)

**Phase to address:**
Phase 1 (must be the first thing done, or done alongside the first tool migration). The test helper refactor is a prerequisite, not a follow-up.

---

### Pitfall 3: Docstring-Schema Drift After Format Change

**What goes wrong:**
All 9 tools have detailed docstrings showing the JSON response format (curly braces, quoted keys, type annotations). FastMCP reads these docstrings verbatim and sends them to LLM clients as tool descriptions. After switching to TOON encoding, the docstrings still describe JSON structure but the actual output is TOON. The LLM client tries to parse responses as JSON based on the description, causing confusion or parsing failures.

**Why it happens:**
Docstrings are easy to forget because they are prose, not code. The encoder swap is a one-line change per tool; updating 9 multi-line docstrings with TOON examples is tedious but mandatory. The project already identified this risk (staleness test in PROJECT.md requirements), which is a good sign.

**How to avoid:**
1. Update docstrings in the SAME commit as the encoder swap for each tool. Never merge a tool with TOON encoding but JSON docstrings.
2. Implement the staleness test early. It should verify that field names mentioned in docstrings match field names in actual tool output. This catches both missing fields and format description mismatches.
3. TOON docstrings should show TOON format examples, not JSON. Show what the LLM will actually receive.

**Warning signs:**
- Docstrings still containing `{`, `}`, `"key":` patterns after TOON migration
- LLM clients attempting `json.loads()` on TOON responses (suggests the description told them to expect JSON)

**Phase to address:**
Every phase that touches tool output. The staleness test should be implemented in Phase 1 and run in CI from that point forward.

---

### Pitfall 4: Pre-Release Library Dependency Risk

**What goes wrong:**
`toon-format` is at version 0.9.0-beta.1. The PyPI page explicitly states "API may change before 1.0.0 release." The `encode()` signature, `EncodeOptions` fields, or normalization behavior could change between the beta and stable release. A project that pins `>=0.9.0b1` may break on upgrade; one that pins `==0.9.0b1` may miss important fixes.

**Why it happens:**
The library is new and pre-1.0. This is inherent risk with early-adopter dependencies. The TOON spec itself appears stable, but the Python implementation is still maturing.

**How to avoid:**
1. Pin the exact version in `pyproject.toml`: `toon-format==0.9.0b1`. Do not use range specifiers.
2. Wrap all TOON calls behind a thin module (`src/serialization.py` or similar) so that if the API changes, you update one file, not 9 tool files.
3. Write integration tests that exercise `encode()` with representative data (nested dicts, lists of dicts, None values, ISO datetime strings) to catch behavioral changes on upgrade.
4. Monitor the GitHub repo for 1.0 release and plan an upgrade task.

**Warning signs:**
- `uv lock` pulling a newer version than expected
- `encode()` signature changes in changelog
- New warnings from the normalization layer after a version bump

**Phase to address:**
Phase 1 (dependency addition). The wrapper module should be established at the same time the dependency is added.

---

### Pitfall 5: Partial Migration Leaves Inconsistent Client Experience

**What goes wrong:**
If tools are migrated one-at-a-time over multiple PRs, the LLM client receives a mix of JSON and TOON responses during the migration window. LLMs handle ambiguous formats poorly -- they may try to parse TOON as JSON or vice versa, especially if some tool descriptions say JSON and others say TOON.

**Why it happens:**
Incremental migration feels safer. "Let's do one tool first and see how it goes." But the MCP protocol does not have per-tool format negotiation. The client sees all tools as belonging to the same server and expects consistent behavior.

**How to avoid:**
1. Migrate all 9 tools in a single phase/PR. The actual code change per tool is minimal (replace `json.dumps(x)` with `toon_format.encode(x)`), so the batch size is manageable.
2. If phasing is necessary for risk management, split by tool category (schema tools, query tools, analysis tools) but merge each batch atomically and update all docstrings in that batch.
3. Never deploy a state where some tools return JSON and others return TOON.

**Warning signs:**
- Multiple open PRs each touching one tool's serialization
- A main branch where `git grep json.dumps` still finds hits in tool files alongside `toon_format.encode` in others

**Phase to address:**
Architectural decision before Phase 1. Commit to atomic migration scope.

---

### Pitfall 6: NaN/Infinity Float Normalization Changes Semantics

**What goes wrong:**
TOON normalizes `float('nan')` and `float('inf')` to `None` (null). JSON's `json.dumps()` raises `ValueError` on these by default (or outputs non-standard `NaN`/`Infinity` with `allow_nan=True`). If any database query returns NaN or Infinity values (possible in computed columns or analysis tool statistics like `std_dev`), the behavior changes silently: instead of an error or a non-standard token, the client gets `null`.

**Why it happens:**
SQL Server can return special float values in edge cases (e.g., `STDEV` of a single-row column). The `get_column_info` tool computes `std_dev` which could be `None` or `NaN` depending on the SQL Server response and how SQLAlchemy maps it.

**How to avoid:**
1. Audit the data pipeline for float fields: `std_dev`, `mean_value`, `min_value`, `max_value` in column stats; `execution_time_ms` in query results.
2. Add explicit NaN/Infinity handling BEFORE the TOON encoding step: `None if math.isnan(v) or math.isinf(v) else v`. This makes the normalization explicit in your code rather than relying on TOON's silent behavior.
3. Document that TOON normalizes these values so future developers understand why.

**Warning signs:**
- Analysis tools returning `null` for statistics that should have numeric values
- Differences between JSON and TOON output for the same query (useful during testing)

**Phase to address:**
Phase 1, specifically when migrating analysis tools. Add the explicit handling as part of the migration.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Calling `toon_format.encode()` directly in each tool function | Simple, no abstraction overhead | 9 call sites to update if API changes; no centralized options config | Never -- use a wrapper from day one |
| Skipping TOON decode in tests, comparing raw strings | Faster test migration | Tests become brittle to TOON formatting changes (whitespace, delimiter) | Never -- always parse then assert on structure |
| Leaving JSON docstring format and just noting "returns TOON" | Quick migration | LLM clients get misleading structural hints; defeats purpose of docstrings | Never -- docstrings must show actual format |
| Not pinning toon-format version | Picks up fixes automatically | Beta API could break on upgrade | Never during pre-1.0 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FastMCP docstrings | Updating the code but not the docstring; FastMCP sends stale descriptions to clients | Treat docstring updates as part of the serialization change, not documentation cleanup |
| `json.dumps(result, default=str)` | `get_column_info` uses `default=str` as a catch-all serializer for datetime etc. TOON has no equivalent parameter -- unsupported types go to null, not to `str()` | Ensure all values are primitives before calling `encode()`. The `default=str` safety net vanishes with TOON. |
| MCP protocol transport | Assuming TOON output needs special content-type headers or transport changes | MCP tools return strings; the transport does not care about format. TOON is just a different string. No protocol changes needed. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Double serialization: `json.dumps()` then `encode()` on the JSON string | Output is a TOON-encoded JSON string literal (quoted, escaped) instead of structured TOON | Replace `json.dumps()` calls, do not wrap them. Pass the dict directly to `encode()`. | Immediately -- output is wrong, not just slow |
| Encoding large query results (10K rows) | Slow response times if TOON encoder is not optimized for large arrays | Benchmark `encode()` with 10K-row tabular data before committing to it. If too slow, consider encoding only the rows array separately. | At scale (large execute_query results) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No security-specific risks for this migration | TOON is a serialization format change, not a trust boundary change | N/A -- query validation, auth, and read-only enforcement are unchanged |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| TOON output without updated docstrings | LLM client cannot parse responses correctly, tool becomes unusable | Always update docstrings atomically with format change |
| Error responses in TOON | Error responses are small (low token savings) and benefit from JSON's universality for debugging | Consider: keep error responses in JSON, only encode success responses in TOON. OR: encode everything in TOON for consistency. Decide explicitly. |

## "Looks Done But Isn't" Checklist

- [ ] **Serialization swap:** `json.dumps` replaced -- verify `default=str` catch-all is also handled (get_column_info uses it)
- [ ] **Docstrings:** Updated to show TOON format -- verify no `{`, `"key":` JSON artifacts remain
- [ ] **Test helpers:** `json.loads()` calls replaced -- verify not just in unit tests but integration tests (6 files, 64 occurrences)
- [ ] **Staleness test:** Implemented and passing -- verify it catches real drift, not just field names
- [ ] **Error paths:** All error returns also use TOON (or explicitly documented as JSON) -- verify early-return validation errors, not just happy path
- [ ] **`to_dict()` still called:** Dataclass serialization still goes through `to_dict()` before `encode()` -- verify no raw dataclass passed to encoder
- [ ] **Float edge cases:** `NaN`/`Infinity` handling explicit -- verify with a test that passes `float('nan')` through the pipeline

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Silent null coercion (Pitfall 1) | LOW | Add `.value`/`.to_dict()` calls; no architectural change needed |
| Test suite breakage (Pitfall 2) | MEDIUM | Introduce `parse_tool_response()` helper, update 64 call sites across 6 files |
| Docstring drift (Pitfall 3) | LOW | Update docstrings; tedious but straightforward |
| Library API break (Pitfall 4) | LOW if wrapper exists, HIGH if 9 direct call sites | Update wrapper module; or update 9 tool files + tests |
| Partial migration inconsistency (Pitfall 5) | MEDIUM | Accelerate remaining tool migrations; possible hotfix to revert partial tools to JSON |
| NaN/Infinity data corruption (Pitfall 6) | LOW | Add explicit float sanitization; one utility function |
| Double serialization (Performance) | LOW | Remove the `json.dumps()` call; fix is obvious once identified |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Silent null coercion | Phase 1: Architecture decision -- TOON replaces json.dumps at boundary only | Unit test with raw enum/dataclass confirms encode behavior |
| Test suite breakage | Phase 1: Test infrastructure prep (before any tool changes) | All 64 json.loads calls go through helper; green tests on JSON still |
| Docstring drift | Every phase that touches tools; staleness test in Phase 1 | Staleness test in CI catches any mismatch |
| Pre-release dependency | Phase 1: Dependency addition | Pinned version in pyproject.toml; wrapper module exists |
| Partial migration | Phase 1: Architectural decision (atomic scope) | No main branch state with mixed formats |
| Float normalization | Phase 1: Analysis tool migration specifically | Test with NaN/Infinity input data |

## Sources

- Codebase inspection: 9 MCP tools across 3 files, 64 `json.loads` test call sites
- TOON Python library source: `normalize.py` confirms Enum/dataclass -> null behavior (GitHub toon-format/toon-python)
- PyPI: toon-format 0.9.0b1 is beta, "API may change before 1.0.0"
- PROJECT.md: Confirms hard switch, no JSON fallback, staleness test requirement

---
*Pitfalls research for: TOON response format migration in dbmcp*
*Researched: 2026-03-04*
