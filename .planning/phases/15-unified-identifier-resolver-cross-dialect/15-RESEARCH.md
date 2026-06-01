# Phase 15: Unified identifier resolver (cross-dialect) - Research

**Researched:** 2026-05-28
**Domain:** SQL identifier parsing/normalization across dialects (MSSQL/Databricks/generic) inside an MCP tool layer
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Resolver lives in a new standalone module `src/db/identifiers.py` with a `resolve_identifier(...)` function. Parsing + conflict logic is dialect-agnostic and lives here; dialect-specific facts come from new `DialectStrategy` properties.
- **D-02:** Resolver returns a frozen dataclass `ResolvedIdentifier(catalog: str | None, schema: str | None, table: str)` — typed, self-documenting, no positional misorder risk across 5 call sites.
- **D-03:** Invoked at each `@mcp.tool` boundary. Each tool calls the resolver, then passes already-normalized `(catalog, schema, table)` down to `MetadataService`. Service methods stop defaulting and consume resolved parts. Resolution stays in one layer; tools own user-input interpretation.
- **D-04:** Conflict = disagreement only. `table_name='sales.orders'` + `schema_name='sales'` → OK (agree). `+ schema_name='hr'` → error. Redundant-but-consistent input is allowed.
- **D-05:** Resolver raises `ValueError` (already mapped to error-response at every tool boundary). Messages name the specific conflict or depth. Do NOT introduce a new exception type — error-class cleanup is deferred.
- **D-06:** Quoting/splitting strategy deferred to research (resolved below). Requirement: a table literally named `my.table` (quoted: `[my.table]`, `` `my.table` ``) must parse as one part.
- **D-07:** `catalog` errors everywhere on non-Databricks (dialect with max depth < 3). Unify all five tools — the 3 existing tools' `catalog` docstrings ("Ignored for non-Databricks") change to *rejected*. ⚠ Backward-incompatible on MSSQL/generic for `list_schemas`/`list_tables`/`get_table_schema`.
- **D-08:** New `DialectStrategy.default_schema` property: MSSQL → `'dbo'`; generic → `None`; Databricks → `None` (no hardcoded name; session/engine default).
- **D-09:** New `DialectStrategy.max_identifier_depth` (or equivalent) property: Databricks=3, MSSQL=2, generic=1.
- **D-10:** No-schema path: resolver returns `schema=None` for generic; metadata calls pass `schema=None` to the SQLAlchemy inspector. No synthetic fallback.
- **D-11:** Remove `schema_name="dbo"` from the 5 tool signatures AND the `MetadataService`/`query.py` methods. Defaults become `None`; resolver/`default_schema` supplies the value.
- **D-12:** SC2 shared test matrix = exhaustive parametrized unit tests on `resolve_identifier`, PLUS one thin parametrized test asserting each of the 5 tools routes through the resolver and surfaces its `ValueError`.
- **D-13:** Fix the `src/tools/` → `src/mcp_server/` path slip in ROADMAP.md Phase 15 SC4 text. **(See note below — already corrected.)**

### Claude's Discretion
- Exact property names (`max_identifier_depth`, `default_schema`) and frozen-dataclass field naming.
- Test file placement/factoring (per TESTING.md).
- Exact error-message phrasing (D-05 gives templates).

### Deferred Ideas (OUT OF SCOPE)
- Error-class taxonomy (`ConfigurationError`) — deferred to a dedicated tech-debt pass; D-05 stays `ValueError`.
- `list_catalogs`/`list_databases` tool — DISC-01 backlog.
- Row-limit naming / `sample_size` typing inconsistencies — deferred out of v2.1.
- Do NOT hardcode a Databricks default schema name like `'main'`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-03 | Shared resolver parses `table_name` into 1/2/3 parts per dialect depth; over-depth → clear error naming expected depth | `sqlglot.to_table(...).parts` reliably counts ALL parts including over-depth overflow (verified). Depth cap from new `max_identifier_depth` property. |
| IDENT-04 | Conflict between `table_name` leading segment and matching explicit param → named-conflict error; no silent override | Resolver compares parsed leading parts to explicit `catalog`/`schema_name`; raises `ValueError` on disagreement (D-04). Pure in-module logic. |
| IDENT-05 | `get_sample_data` gains optional `catalog` (Databricks-only); MSSQL/generic → dialect-inappropriate-param error | `get_sample_data` currently lacks `catalog` (verified). `except ValueError` handler already present at boundary (verified). |
| IDENT-06 | `get_column_info` gains optional `catalog`; same gate | `get_column_info` currently lacks `catalog` (verified). `except ValueError` handler present (verified). |
| IDENT-07 | Each dialect advertises its own `default_schema` on `DialectStrategy`; no hardcoded `schema_name='dbo'` in signatures | New `default_schema` property follows existing `@property` Protocol pattern. All `dbo` defaults located (verified). |
</phase_requirements>

## Summary

The central open question (D-06) resolves decisively in favor of **using `sqlglot.to_table(table_name, dialect=...)` for splitting**, not hand-rolling a quote-aware dot-splitter. sqlglot 30.7.0 is already an installed, pinned dependency (`sqlglot>=30.7.0,<31.0.0`), the `DialectStrategy` Protocol already exposes a `sqlglot_dialect` property that maps cleanly to all three dialects in play, and `sqlglot.to_table(...).parts` satisfies the hard requirement from D-06 across all three dialects: a quoted dotted table (`[my.table]`, `` `my.table` ``, `"my.table"`) parses as exactly one part, and unquoted `catalog.schema.table` parses as three. Hand-rolling would re-implement per-dialect quote rules (brackets, backticks, double-quotes, escape doubling) that sqlglot already handles and the codebase already trusts for query parsing/validation — re-implementing them is a DRY violation and a new bug surface.

There is **one critical correctness trap** the planner must encode: `to_table("a.b.c.d")` does **not** raise on over-depth — it silently absorbs the 4th segment into a `Dot` expression, so `Table.name` returns only `'d'` and `Table.catalog`/`Table.db`/`Table.name` count to 3 even though 4 parts were supplied. The depth check MUST use `Table.parts` (the ordered `list[Identifier]`), which correctly returns 4 elements for `a.b.c.d`. Counting `catalog`/`db`/`name` attributes would silently swallow over-depth input and violate IDENT-03.

A second trap: sqlglot does **not** sanitize. `to_table("a; DROP TABLE b")` returns a single `Identifier` whose `.name` is the literal `"a; DROP TABLE b"` — no error. sqlglot splits; it does not validate safety. The resolver therefore must continue to rely on the existing downstream `dialect.quote_identifier(...)` (already used in `query.py:119`) to produce safe SQL. The resolver's job is structural decomposition and conflict detection, not injection defense.

**Primary recommendation:** Implement `resolve_identifier` in `src/db/identifiers.py` using `sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)`, count `result.parts`, validate length against a new `dialect.max_identifier_depth`, map ordered parts right-to-left onto `(table, schema, catalog)`, compare any leading parts against explicit `catalog`/`schema_name` for conflicts (D-04), and fill missing schema from `dialect.default_schema`. Return a frozen `ResolvedIdentifier`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Parse `table_name` → parts | API/Backend (`src/db/identifiers.py`) | — | Dialect-agnostic parsing logic; one layer (D-01). |
| Dialect depth / default schema facts | API/Backend (`DialectStrategy` impls) | — | Dialect-owned behavior is the established pattern (D-08/D-09). |
| User-input interpretation (call resolver) | API/Backend (`@mcp.tool` in `src/mcp_server/`) | — | Tools own user-input interpretation; pass normalized parts down (D-03). |
| Quoting/safe SQL emission | API/Backend (`dialect.quote_identifier`, `query.py`) | — | Existing; resolver does NOT sanitize. |
| Error → MCP response mapping | API/Backend (`@mcp.tool` boundary) | — | `except ValueError` already maps to error response (verified). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlglot` | 30.7.0 (installed; pinned `>=30.7.0,<31.0.0`) | Dialect-aware identifier parsing via `to_table(...).parts` | Already a project dependency, already mapped per-dialect via `DialectStrategy.sqlglot_dialect`, already trusted for query validation. No new dependency. |
| `dataclasses` (stdlib) | Python 3.11+ | `@dataclass(frozen=True)` for `ResolvedIdentifier` | Matches CONVENTIONS.md ("Dataclasses use CamelCase"); zero deps. |

### Supporting
None required. The resolver is pure-Python over sqlglot + stdlib.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sqlglot.to_table().parts` | Hand-rolled quote-aware dot-splitter keyed off `dialect.quote_identifier` | Hand-roll would re-implement bracket/backtick/double-quote rules + escape doubling (`]]`) that sqlglot already handles. New bug surface, DRY violation, harder to explain. **Rejected.** |
| `sqlglot.to_table()` | `sqlglot.parse_one(s, into=exp.Table)` | Functionally equivalent for this use; `to_table` is the dedicated, clearer helper. Prefer `to_table`. |

**Installation:** None — `sqlglot` already declared in `pyproject.toml:27`.

**Version verification:** `uv run python -c "import sqlglot; print(sqlglot.__version__)"` → `30.7.0` [VERIFIED: local import]. Declared pin `sqlglot>=30.7.0,<31.0.0` [VERIFIED: pyproject.toml:27].

## Package Legitimacy Audit

No new external packages are installed in this phase. `sqlglot` is a pre-existing, pinned dependency already in active use for query validation. Audit not applicable.

## Architecture Patterns

### System Architecture Diagram

```
@mcp.tool (e.g. get_sample_data)
   |  raw user input: table_name, schema_name?, catalog?
   v
resolve_identifier(table_name, schema_name, catalog, dialect)   [src/db/identifiers.py]
   |
   |-- sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)
   |       -> Table.parts : list[Identifier]   (handles quoted dotted names + over-depth overflow)
   |
   |-- len(parts) > dialect.max_identifier_depth ?  --yes--> raise ValueError("...allow at most N parts...")
   |
   |-- map parts right->left: table, [schema], [catalog]
   |
   |-- catalog provided but max_identifier_depth < 3 ? --yes--> raise ValueError(catalog-inappropriate)  (D-07)
   |
   |-- leading part disagrees with explicit param ? --yes--> raise ValueError("Conflicting schema/catalog...")  (D-04)
   |
   |-- schema still None ? -> fill from dialect.default_schema (D-08/D-10)
   v
ResolvedIdentifier(catalog, schema, table)   (frozen)
   |
   v
MetadataService / QueryService methods  (no longer default to "dbo"; consume resolved parts; schema=None -> inspector default)
   |
   v
dialect.quote_identifier(...) -> safe SQL    (UNCHANGED; resolver does not sanitize)
```

File-to-implementation mapping belongs in the Component Responsibilities table below.

### Recommended Project Structure
```
src/db/
├── identifiers.py        # NEW: resolve_identifier() + ResolvedIdentifier (D-01/D-02)
├── dialects/
│   ├── protocol.py       # ADD: default_schema, max_identifier_depth properties to Protocol
│   ├── mssql.py          # ADD: default_schema='dbo', max_identifier_depth=2
│   ├── databricks.py     # ADD: default_schema=None, max_identifier_depth=3
│   └── generic.py        # ADD: default_schema=None, max_identifier_depth=1
├── metadata.py           # REMOVE schema_name="dbo" defaults -> None
└── query.py              # REMOVE schema_name="dbo" default -> None (:81)
src/mcp_server/
├── schema_tools.py       # 3 tools: drop dbo default; catalog Ignored->rejected; route through resolver
├── query_tools.py        # get_sample_data: add catalog; drop dbo default; route through resolver
└── analysis_tools.py     # get_column_info: add catalog; drop dbo default; route through resolver
```

### Pattern 1: Dialect-aware identifier split with `to_table().parts`
**What:** Use sqlglot to split a possibly-qualified, possibly-quoted identifier into ordered parts.
**When to use:** Always, for the resolver's parsing step.
**Example:**
```python
# Source: sqlglot 30.7.0, verified via local probe 2026-05-28
import sqlglot

def split_parts(table_name: str, sqlglot_dialect: str | None) -> list[str]:
    # to_table handles MSSQL [brackets], Databricks `backticks`, ANSI "double-quotes".
    # .parts returns ordered list[Identifier]; CRITICAL: it counts over-depth overflow
    # (e.g. "a.b.c.d" -> 4 parts) which Table.name/db/catalog alone would silently swallow.
    table = sqlglot.to_table(table_name, dialect=sqlglot_dialect)
    return [ident.name for ident in table.parts]  # .name is the UNQUOTED text
```

Verified behavior (local probes, sqlglot 30.7.0):
- `to_table("sales.orders", "tsql").parts` → `['sales', 'orders']`
- `to_table("cat.sales.orders", "databricks").parts` → `['cat', 'sales', 'orders']`
- `to_table("[my.table]", "tsql").parts` → `['my.table']` (one part) ✓ D-06
- `to_table("`my.table`", "databricks").parts` → `['my.table']` ✓ D-06
- `to_table('"my.table"', None).parts` → `['my.table']` ✓ D-06
- `to_table("main.sales.`my.table`", "databricks").parts` → `['main', 'sales', 'my.table']` ✓
- `to_table("a.b.c.d", "databricks").parts` → `['a','b','c','d']` (4 parts — over-depth detectable) ✓ IDENT-03

### Pattern 2: Right-to-left part mapping
**What:** The rightmost part is always the table; preceding parts fill schema then catalog.
**When to use:** After length validation against `max_identifier_depth`.
**Example:**
```python
# table is always parts[-1]; schema/catalog fill leftward as available
parts = split_parts(table_name, dialect.sqlglot_dialect)
if len(parts) > dialect.max_identifier_depth:
    raise ValueError(
        f"{dialect.name} identifiers allow at most {dialect.max_identifier_depth} parts; "
        f"got {len(parts)}: {table_name}"
    )
table = parts[-1]
parsed_schema = parts[-2] if len(parts) >= 2 else None
parsed_catalog = parts[-3] if len(parts) >= 3 else None
```

### Anti-Patterns to Avoid
- **Counting `Table.catalog`/`Table.db`/`Table.name` to detect depth:** Over-depth input (`a.b.c.d`) leaves `Table.name == 'd'` and reports 3 populated attributes while a 4th part hides in a `Dot` expression. Use `Table.parts` length. This is the single highest-risk mistake for IDENT-03.
- **Treating sqlglot parsing as sanitization:** `to_table("a; DROP TABLE b")` returns one `Identifier` named `"a; DROP TABLE b"` with NO error. Keep relying on `dialect.quote_identifier` downstream for safe SQL emission.
- **Hardcoding `'main'` as Databricks default schema:** Explicitly warned against in Phase 14; `default_schema` is `None` for Databricks.
- **Filling schema from `default_schema` for generic:** D-10 says generic returns `schema=None`; the SQLAlchemy inspector applies the connection's default. `default_schema` is `None` for generic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Splitting `catalog.schema.table` with quoted dotted names | Custom dot-splitter aware of `[]`, `` ` ``, `"` and escape doubling | `sqlglot.to_table(...).parts` | sqlglot already encodes every dialect's quote/escape rules; the codebase already trusts it for query validation. Hand-rolling duplicates that knowledge and adds bugs (KISS/DRY). |
| Mapping our dialect → parser dialect string | New mapping table | Existing `DialectStrategy.sqlglot_dialect` (`tsql`/`databricks`/`None`/postgres/mysql/sqlite) | Mapping already exists and is tested (`generic.py:_URL_SCHEME_TO_SQLGLOT`). |

**Key insight:** The hard part of identifier parsing is the per-dialect quoting/escaping matrix, and that already lives in sqlglot — which this project already ships and already uses. Re-implementing it is pure downside.

## Common Pitfalls

### Pitfall 1: Over-depth silently swallowed
**What goes wrong:** A 4-part Databricks identifier or 3-part MSSQL identifier passes validation because `Table.name`/`db`/`catalog` only expose 3 slots.
**Why it happens:** sqlglot folds the extra leading-but-overflow segment into a `Dot` AST node rather than raising.
**How to avoid:** Validate `len(Table.parts)` against `max_identifier_depth`. Verified: `to_table("a.b.c.d").parts` has length 4.
**Warning signs:** A test like "Databricks 4-part raises" passes only if you count `parts`, not attributes.

### Pitfall 2: sqlglot doesn't reject garbage
**What goes wrong:** `a; DROP TABLE b`, `a b` (space) parse to a single identifier carrying the literal string — no error.
**Why it happens:** sqlglot treats an unparseable-as-multiple token as one quoted identifier.
**How to avoid:** Do not rely on sqlglot for validation/sanitization. Downstream `quote_identifier` (query.py:119) remains the safety boundary. If stricter input validation is desired it is a separate concern — but note `to_table("a.")` and `to_table("")` DO raise `ParseError` (which would surface as an unexpected `Exception`, not `ValueError`). The resolver should either catch `sqlglot.ParseError` and re-raise as `ValueError` (recommended, keeps D-05's clean error mapping) or document that malformed input yields a generic failure.

### Pitfall 3: Backward-incompatible catalog gate (D-07)
**What goes wrong:** Existing MSSQL/generic callers passing `catalog` to `list_schemas`/`list_tables`/`get_table_schema` previously got silent-ignore; now they get a `ValueError` error response.
**Why it happens:** Unifying all five tools through one gate (`max_identifier_depth < 3` → reject `catalog`).
**How to avoid:** Plan must size this as an intentional breaking change; update the three docstrings ("Ignored for non-Databricks" → "rejected"). Tests must assert the new error, and any internal callers passing `catalog=None` are unaffected (gate fires only when `catalog` is truthy).

### Pitfall 4: Stray `dbo` defaults beyond the D-11 list
**What goes wrong:** D-11 enumerates input-parameter `dbo` defaults, but `metadata.py:919` has `fk.get("referred_schema", "dbo")` — a *result-mapping* default that reports `'dbo'` as the FK target schema when the inspector omits it.
**Why it happens:** It's an output field, not a signature default, so it's outside D-11's literal scope.
**How to avoid:** Planner should explicitly decide: leave it (it's a display default for FK targets, not a query-routing default) or change to `None`. Flagging so it's a conscious choice, not an oversight. **Recommendation:** out of scope for SC4 (SC4 targets signatures), but note it in the plan so the next dbo audit catches it.

## Code Examples

### Resolver skeleton (illustrative — planner/executor own final shape)
```python
# Source: synthesized from verified sqlglot 30.7.0 behavior + CONTEXT.md D-01..D-10
from dataclasses import dataclass
import sqlglot

@dataclass(frozen=True)
class ResolvedIdentifier:
    catalog: str | None
    schema: str | None
    table: str

def resolve_identifier(
    table_name: str,
    schema_name: str | None,
    catalog: str | None,
    dialect,  # DialectStrategy
) -> ResolvedIdentifier:
    try:
        parsed = sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)
    except sqlglot.ParseError as e:
        raise ValueError(f"Could not parse table_name '{table_name}': {e}") from e
    parts = [p.name for p in parsed.parts]

    if catalog and dialect.max_identifier_depth < 3:
        raise ValueError(
            f"catalog is not supported on {dialect.name} (max identifier depth "
            f"{dialect.max_identifier_depth})"
        )
    if len(parts) > dialect.max_identifier_depth:
        raise ValueError(
            f"{dialect.name} identifiers allow at most {dialect.max_identifier_depth} "
            f"parts; got {len(parts)}: {table_name}"
        )

    table = parts[-1]
    parsed_schema = parts[-2] if len(parts) >= 2 else None
    parsed_catalog = parts[-3] if len(parts) >= 3 else None

    # Conflict detection (D-04: disagreement only)
    if parsed_schema and schema_name and parsed_schema != schema_name:
        raise ValueError(
            f"Conflicting schema: table_name specifies '{parsed_schema}' "
            f"but schema_name='{schema_name}'"
        )
    if parsed_catalog and catalog and parsed_catalog != catalog:
        raise ValueError(
            f"Conflicting catalog: table_name specifies '{parsed_catalog}' "
            f"but catalog='{catalog}'"
        )

    final_schema = parsed_schema or schema_name or dialect.default_schema
    final_catalog = parsed_catalog or catalog
    return ResolvedIdentifier(catalog=final_catalog, schema=final_schema, table=table)
```

### Dialect property additions (follow existing `@property` pattern)
```python
# protocol.py — add to DialectStrategy Protocol
@property
def default_schema(self) -> str | None:
    """Default schema for this dialect, or None if the engine/connection decides."""
    ...

@property
def max_identifier_depth(self) -> int:
    """Max number of dotted identifier parts (Databricks=3, MSSQL=2, generic=1)."""
    ...

# mssql.py
@property
def default_schema(self) -> str | None: return "dbo"
@property
def max_identifier_depth(self) -> int: return 2

# databricks.py
@property
def default_schema(self) -> str | None: return None  # no hardcoded 'main'
@property
def max_identifier_depth(self) -> int: return 3

# generic.py
@property
def default_schema(self) -> str | None: return None
@property
def max_identifier_depth(self) -> int: return 1
```

## Runtime State Inventory

This is a code refactor (parsing logic + signatures + properties). No stored data, live service config, OS state, or secrets are renamed or migrated.

- **Stored data:** None — no datastore keys/IDs change. Verified: resolver operates on in-memory request params only.
- **Live service config:** None — no external service configuration references identifier-resolver internals.
- **OS-registered state:** None.
- **Secrets/env vars:** None — env-var resolution (`${DBX_CATALOG}` etc.) is upstream in connection config (Phase 14 scope), unaffected by resolver.
- **Build artifacts / installed packages:** None — no package rename; `sqlglot` already installed. The new `src/db/identifiers.py` is picked up automatically (no entry-point/console-script change).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `schema_name="dbo"` defaults scattered across tools + service methods | Per-dialect `default_schema` property; `None` defaults filled by resolver | This phase (IDENT-07) | SQLite/Databricks no longer silently get `'dbo'`. |
| `catalog` silently ignored on non-Databricks (3 schema tools) | `catalog` rejected with `ValueError` on dialects with depth < 3 (all 5 tools) | This phase (D-07) | Backward-incompatible; intentional. |
| No identifier parser; ad-hoc `schema.table` assumptions | One `resolve_identifier` over `sqlglot.to_table().parts` | This phase | Quoted dotted names handled correctly; over-depth rejected. |

**Deprecated/outdated:**
- D-13's premise (ROADMAP says `src/tools/`): **stale.** Verified `grep -n 'src/tools' .planning/ROADMAP.md` → no matches; SC4 text already reads `src/mcp_server/`. The slip appears already corrected. Planner should treat D-13 as a no-op (or a quick confirm-and-close), not a real edit.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Catching `sqlglot.ParseError` and re-raising as `ValueError` is the desired handling for malformed `table_name` (vs. letting it surface as generic `Exception`) | Pitfall 2 / Code Examples | Low — keeps D-05's clean error mapping; planner can confirm. Without it, `to_table("a.")` / `""` raise `ParseError` which hits the generic `except Exception` and yields a less clean message. |
| A2 | `metadata.py:919` `referred_schema` default `"dbo"` is intentionally out of SC4 scope (output field, not signature) | Pitfall 4 | Low — it's a display value for FK targets, not query routing; flagged for conscious decision. |

**Note:** Both items are LOW risk and surfaced for the planner to confirm, not blockers.

## Open Questions (RESOLVED)

1. **Malformed-input handling (ties to A1)**
   - What we know: `to_table("a.")`, `to_table("")` raise `sqlglot.ParseError`; `to_table("a; DROP TABLE b")` does NOT raise (returns one identifier).
   - What's unclear: Whether the resolver should normalize `ParseError` → `ValueError` (recommended) or leave it.
   - Recommendation: Catch `sqlglot.ParseError` and re-raise as `ValueError` so all resolver failures map uniformly through the existing `except ValueError` boundary (D-05).

2. **`metadata.py:919` `referred_schema` default (ties to A2)**
   - What we know: It's a result-mapping default reporting `'dbo'` for FK target schema, outside D-11's enumerated signature defaults.
   - What's unclear: In/out of SC4 scope.
   - Recommendation: Out of SC4 (which targets signatures); note in plan for a future dbo audit.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `sqlglot` | resolver parsing | ✓ | 30.7.0 | — (pinned dependency) |
| `uv` | run tests/tools | ✓ (project mandate) | — | — |

No missing dependencies. No external services needed (pure in-memory parsing).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio (asyncio_mode = "auto") + pytest-cov |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=["tests"]) |
| Quick run command | `uv run pytest tests/unit/test_identifiers.py -x` (new file) |
| Full suite command | `uv run pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDENT-03 | depth parse + over-depth error per dialect | unit (parametrized) | `uv run pytest tests/unit/test_identifiers.py -k depth -x` | ❌ Wave 0 |
| IDENT-04 | conflict/agreement detection | unit (parametrized) | `uv run pytest tests/unit/test_identifiers.py -k conflict -x` | ❌ Wave 0 |
| IDENT-05 | get_sample_data catalog gate + routes through resolver | unit (thin boundary) | `uv run pytest tests/unit/test_query_tools.py -k catalog -x` | ⚠ extend |
| IDENT-06 | get_column_info catalog gate + routes through resolver | unit (thin boundary) | `uv run pytest tests/unit/test_analysis_tools.py -k catalog -x` | ⚠ extend |
| IDENT-07 | no `dbo` in signatures; default_schema supplies it | unit | `uv run pytest tests/unit/test_dialects -k default_schema -x` | ⚠ extend |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_identifiers.py -x`
- **Per wave merge:** `uv run pytest tests/`
- **Phase gate:** Full suite green + 85% coverage floor maintained (documented floor; NOT enforced via `--cov-fail-under` in addopts — verify manually with `uv run pytest tests/ --cov=src`).

### Wave 0 Gaps
- [ ] `tests/unit/test_identifiers.py` — covers IDENT-03/IDENT-04 (exhaustive parametrized matrix: dialect × depth × conflict/agreement/catalog-gate per D-12).
- [ ] Extend `tests/unit/test_query_tools.py` and `tests/unit/test_analysis_tools.py` — thin parametrized test that each of the 5 tools routes through resolver and surfaces `ValueError` as error response (D-12).
- [ ] Extend dialect tests — assert `default_schema` and `max_identifier_depth` per dialect.
- No framework install needed (pytest already present).

## Security Domain

> `security_enforcement` config key not located in repo config; treating the relevant ASVS category (input validation) as in-scope given this phase parses user-supplied identifiers.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Out of phase scope. |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Resolver validates depth + conflict; **but sqlglot does NOT sanitize**. SQL-safety remains `dialect.quote_identifier` (query.py:119). |
| V6 Cryptography | no | — |

### Known Threat Patterns for {parsing user identifiers}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via crafted `table_name` (e.g. `a; DROP TABLE b`) | Tampering | sqlglot parses it as one literal identifier (no split); downstream `quote_identifier` brackets/backticks/quotes it. The resolver must NOT bypass `quote_identifier`. Verified: existing `query.py:119` quotes both schema and table. |
| Confusing/ambiguous quoted dotted names | Tampering | sqlglot preserves quoted dotted names as single parts (verified) — no ambiguity in split. |

## Sources

### Primary (HIGH confidence)
- Local sqlglot 30.7.0 probes (2026-05-28) — `to_table().parts` behavior across `tsql`/`databricks`/`None`; over-depth `Dot` overflow; quoted-dotted single-part; `ParseError` on malformed; no-sanitization of `a; DROP TABLE b`. All claims tagged "verified via local probe" derive from these.
- `src/db/dialects/protocol.py`, `mssql.py`, `databricks.py`, `generic.py` — existing `sqlglot_dialect` values (`tsql`/`databricks`/`None`+postgres/mysql/sqlite) and `@property` pattern [VERIFIED: file read].
- `src/mcp_server/query_tools.py`, `analysis_tools.py` — `except ValueError → error_message` handlers confirmed; `get_sample_data`/`get_column_info` lack `catalog` [VERIFIED: file read].
- `src/db/metadata.py` (731/781/817/833/852/1126/919), `src/db/query.py:81` — `dbo` default locations [VERIFIED: grep].
- `pyproject.toml:27` — `sqlglot>=30.7.0,<31.0.0` pin [VERIFIED].
- `.planning/ROADMAP.md` — SC4 already reads `src/mcp_server/` (D-13 premise stale) [VERIFIED: grep no `src/tools`].

### Secondary (MEDIUM confidence)
- None required; all critical claims verified by local probe or file read.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- D-06 decision (sqlglot vs hand-roll): HIGH — validated against installed version with the exact D-06 requirement and the over-depth edge case.
- Standard stack: HIGH — sqlglot already installed/pinned/used.
- Architecture/patterns: HIGH — extends existing Protocol + boundary patterns.
- Pitfalls: HIGH — each backed by a verified probe or file read.
- Backward-incompat sizing (D-07): MEDIUM — behavior confirmed in code; exact caller-impact set depends on test coverage the planner adds.

**Research date:** 2026-05-28
**Valid until:** ~2026-06-27 (stable; only risk is a sqlglot major bump, blocked by the `<31.0.0` pin).
