# Phase 8: Dialect Protocol & MSSQL Extraction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 08-dialect-protocol-mssql-extraction
**Areas discussed:** Protocol design, Extraction boundary, Registry & resolution, Module layout

---

## Protocol Design

### Protocol vs ABC

| Option | Description | Selected |
|--------|-------------|----------|
| typing.Protocol (Recommended) | Structural subtyping — implementations don't need to explicitly inherit. Lighter, Pythonic, fits the dataclass-oriented codebase. | ✓ |
| abc.ABC | Nominal subtyping — explicit inheritance. Better IDE support for 'implement all methods', raises TypeError at instantiation if method missing. | |
| You decide | Claude picks based on codebase conventions and what works best for downstream phases. | |

**User's choice:** typing.Protocol
**Notes:** First abstract pattern in the codebase.

### Capability Flags

| Option | Description | Selected |
|--------|-------------|----------|
| Bool properties on protocol | supports_indexes: bool, has_fast_row_counts: bool, etc. Simple, explicit. Checked at call sites. | ✓ |
| Capabilities enum set | capabilities: set[Capability] with values like INDEXES, FAST_ROW_COUNTS. Extensible, one check method. | |
| You decide | Claude picks the approach that fits the codebase best. | |

**User's choice:** Bool properties on protocol
**Notes:** None

### Unsupported Feature Signaling

| Option | Description | Selected |
|--------|-------------|----------|
| Return None + caller checks | fast_row_counts() -> dict | None. Returns None when unsupported; caller falls back to COUNT(*). | |
| Guard with capability flag | Callers check has_fast_row_counts before calling. Method can raise NotImplementedError if called anyway. | |
| You decide | Claude picks based on what produces cleaner call sites. | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

### Protocol Methods

| Option | Description | Selected |
|--------|-------------|----------|
| Those are sufficient | Start with exactly what ROADMAP specifies. Additional methods can be added in later phases as needed. | ✓ |
| Add more now | I have specific methods in mind that should be in the initial protocol. | |

**User's choice:** Those are sufficient
**Notes:** Methods: name, sqlglot_dialect, create_engine, fast_row_counts, quote_identifier, plus capability flags.

---

## Extraction Boundary

### ConnectionManager Split

| Option | Description | Selected |
|--------|-------------|----------|
| Dialect owns engine creation | MssqlDialect.create_engine() handles ODBC strings + Azure AD. ConnectionManager stays dialect-agnostic. | |
| ConnectionManager delegates | ConnectionManager calls dialect.create_engine() internally. Keeps singleton pattern. | |
| You decide | Claude picks based on cleanest separation of concerns. | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

### MetadataService DMV Queries

| Option | Description | Selected |
|--------|-------------|----------|
| DMV queries move to MssqlDialect | MetadataService uses Inspector by default. MssqlDialect provides fast_row_counts() and DMV overrides. | |
| Keep DMVs in MetadataService | MetadataService keeps DMV queries behind dialect_name checks. Dialect only owns engine creation and quoting. | |
| You decide | Claude picks based on three-tier query strategy alignment. | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

### Azure Auth Location

| Option | Description | Selected |
|--------|-------------|----------|
| Move into dialect package | azure_auth.py moves to src/db/dialects/mssql/ as a private module. Keeps MSSQL-specific code co-located. | ✓ |
| Keep standalone, import from dialect | azure_auth.py stays at src/db/azure_auth.py. MssqlDialect imports from it. Simpler diff, less file churn. | |
| You decide | Claude picks based on cleanest import graph. | |

**User's choice:** Move into dialect package
**Notes:** Co-locate all MSSQL-specific code.

---

## Registry & Resolution

### Registry Pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Simple dict registry (Recommended) | Module-level dict mapping str to DialectStrategy class. register_dialect() and get_dialect() functions. | ✓ |
| Auto-discovery via entry_points | Use pkg_resources/importlib.metadata entry points for third-party dialect registration. | |
| You decide | Claude picks simplest approach meeting DIAL-05. | |

**User's choice:** Simple dict registry
**Notes:** None

### Fallback Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Error until GenericDialect exists | In Phase 8, unknown dialects raise error. Phase 10 adds GenericDialect as fallback. | ✓ |
| Fallback to MSSQL | Unknown dialects default to MssqlDialect. Preserves backward compat. | |
| You decide | Claude picks based on fail-fast principle. | |

**User's choice:** Error until GenericDialect exists
**Notes:** Fail-fast over silent misconfiguration.

---

## Module Layout

### Dialect Package Location

| Option | Description | Selected |
|--------|-------------|----------|
| src/db/dialects/ package (Recommended) | Clean namespace under db/, easy to add dialects. | |
| src/dialects/ top-level | Separate from db/ since dialects span multiple concerns. | |
| You decide | Claude picks based on existing codebase organization. | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

### MSSQL Dialect Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Subpackage: src/db/dialects/mssql/ | Directory with __init__.py, azure_auth.py, etc. Room for internals. | |
| Single file + private module | mssql.py + _mssql_auth.py. Flatter, less nesting. | |
| You decide | Claude picks based on volume of MSSQL-specific code. | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

---

## Claude's Discretion

- Unsupported feature signaling (return None vs capability flag guard)
- ConnectionManager/dialect split approach
- DMV query extraction strategy
- Module layout details (package location, MSSQL subpackage vs flat files)

## Deferred Ideas

None — discussion stayed within phase scope.
