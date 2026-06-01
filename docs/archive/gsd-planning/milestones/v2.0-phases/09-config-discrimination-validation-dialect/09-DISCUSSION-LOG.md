# Phase 9: Config Discrimination & Validation Dialect - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 09-config-discrimination-validation-dialect
**Areas discussed:** Config model design, Backward compat, Safe procedure list, Validation plumbing

---

## Config Model Design

### Q1: How should per-dialect config models be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate dataclasses | MssqlConnectionConfig, DatabricksConnectionConfig, GenericConnectionConfig — each with only needed fields | ✓ |
| Base + subclass | Base ConnectionConfig with shared fields, subclasses add dialect-specific | |
| You decide | Claude picks based on field overlap analysis | |

**User's choice:** Separate dataclasses
**Notes:** Clean separation, dialect-specific validation per class. Matches existing flat dataclass style.

### Q2: Should the `dialect` field in TOML be required or optional?

| Option | Description | Selected |
|--------|-------------|----------|
| Optional, default mssql | Omitting defaults to mssql — backward compatible per CONF-01 | |
| Required for non-mssql only | MSSQL can omit, others must specify | |
| Always required | Every connection must state dialect explicitly | ✓ |

**User's choice:** Always required
**Notes:** Overrides CONF-01. User prefers explicit over implicit despite breaking existing configs.

### Q3: Confirmation — Override CONF-01?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, override CONF-01 | Require dialect in every connection. Accept breaking change. | ✓ |
| Keep CONF-01 default | Omitting dialect defaults to mssql | |

**User's choice:** Yes, override CONF-01
**Notes:** Confirmed the breaking change is intentional.

### Q4: How should invalid or unexpected fields be handled?

| Option | Description | Selected |
|--------|-------------|----------|
| Warn and ignore | Log warning for unrecognized fields, skip them | ✓ |
| Error on unknown fields | Strict — reject config with unknown fields | |
| You decide | Claude picks based on existing patterns | |

**User's choice:** Warn and ignore

---

## Backward Compat

### Q1: Error message style for missing `dialect`

| Option | Description | Selected |
|--------|-------------|----------|
| Clear error with fix | ValueError with actionable message suggesting `dialect = "mssql"` | ✓ |
| Hard fail, no guidance | Generic missing field error | |
| You decide | Claude picks based on existing patterns | |

**User's choice:** Clear error with fix

### Q2: Tool params in Phase 9

| Option | Description | Selected |
|--------|-------------|----------|
| Keep old params for now | Phase 9 only changes TOML config. Tool signature unchanged until Phase 10. | ✓ |
| Start trimming now | Begin removing SQL Server-specific tool params | |

**User's choice:** Keep old params for now

---

## Safe Procedure List

### Q1: Where should dialect-specific safe procedure lists live?

| Option | Description | Selected |
|--------|-------------|----------|
| On DialectStrategy | Add safe_procedures property to protocol. MssqlDialect returns 22 sp_ procs, others empty. | ✓ |
| In validation.py | Dict mapping dialect names to procedure sets in validation module | |
| You decide | Claude picks based on separation of concerns | |

**User's choice:** On DialectStrategy

### Q2: Config-level SP allowlist scope

| Option | Description | Selected |
|--------|-------------|----------|
| Global | Config allowed_stored_procedures applies to all dialects | ✓ |
| Per-dialect | Each connection's SP allowlist scoped to its dialect | |
| You decide | Claude picks based on usage patterns | |

**User's choice:** Global

---

## Validation Plumbing

### Q1: How should the dialect reach validate_query()?

| Option | Description | Selected |
|--------|-------------|----------|
| String parameter | validate_query takes sqlglot dialect string. Simple, no coupling. | ✓ |
| DialectStrategy object | Takes full strategy object. Tighter coupling but single param. | |
| You decide | Claude picks based on minimizing changes | |

**User's choice:** String parameter

### Q2: Should validate_query default to 'tsql' or require dialect?

| Option | Description | Selected |
|--------|-------------|----------|
| Default tsql | Backward compatible, existing callers don't break | |
| Required parameter | Force every caller to pass dialect explicitly | ✓ |

**User's choice:** Required parameter
**Notes:** No default — explicit everywhere. ~40+ test calls need updating.

### Q3: How should tests handle the required dialect parameter?

| Option | Description | Selected |
|--------|-------------|----------|
| Update all to pass 'tsql' explicitly | Every test passes dialect='tsql'. Verbose but clear. | ✓ |
| Test helper / fixture | Wrapper or fixture to reduce repetition | |
| You decide | Claude picks based on test conventions | |

**User's choice:** Update all to pass 'tsql' explicitly

---

## Claude's Discretion

- D-12: Internal structure of per-dialect config dataclass fields
- D-13: Whether validate_query takes safe_procedures as separate param or bundled
- D-14: How _parse_connections() dispatches to per-dialect parsers

## Deferred Ideas

None — discussion stayed within phase scope
