# Phase 10: GenericDialect & Tool Interface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 10-genericdialect-tool-interface
**Areas discussed:** Tool interface design, GenericDialect behavior, Dependency separation, Registry fallback

---

## Tool Interface Design

| Option | Description | Selected |
|--------|-------------|----------|
| connection_name + sqlalchemy_url only | Two params only: connection_name (loads from TOML) or sqlalchemy_url (direct URL). Clean break. | ✓ |
| connection_name + sqlalchemy_url + kwargs | Same two primary params, plus a generic **kwargs or key-value dict for dialect-specific overrides. | |

**User's choice:** connection_name + sqlalchemy_url only
**Notes:** Clean break for v2.0

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect from URL scheme | Parse the URL scheme (mssql+pyodbc:// -> mssql, databricks:// -> databricks, else -> generic). | ✓ |
| Require dialect param alongside URL | Add a third optional 'dialect' param to connect_database. | |

**User's choice:** Auto-detect from URL scheme
**Notes:** Zero config for the user

| Option | Description | Selected |
|--------|-------------|----------|
| Remove immediately | Clean break as CONF-03 specifies. v2.0 is the right time. | ✓ |
| Deprecation warnings for one release | Keep old params but log deprecation warnings. | |

**User's choice:** Remove immediately
**Notes:** v2.0 clean break, no deprecation period

---

## GenericDialect Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Map from URL scheme, fallback to None | Maintain mapping of known SQLAlchemy URL schemes to sqlglot dialect names. Unknown -> None. | ✓ |
| Always use None (generic SQL) | Always pass dialect=None to sqlglot. | |
| Store dialect string in config | Add optional sqlglot_dialect field to GenericConnectionConfig. | |

**User's choice:** Map from URL scheme, fallback to None
**Notes:** Covers 90% of cases automatically

| Option | Description | Selected |
|--------|-------------|----------|
| ANSI double-quotes always | Use ANSI SQL standard double-quote quoting. | ✓ |
| Detect from SQLAlchemy engine | Read quoting style from engine's dialect.identifier_preparer at runtime. | |

**User's choice:** ANSI double-quotes always

| Option | Description | Selected |
|--------|-------------|----------|
| supports_indexes=True, has_fast_row_counts=False | Most generic DBs support indexes via Inspector. No fast row count path. | ✓ |
| Both False (conservative) | Assume nothing about generic databases. | |

**User's choice:** supports_indexes=True, has_fast_row_counts=False

---

## Dependency Separation

| Option | Description | Selected |
|--------|-------------|----------|
| Core = zero DB drivers | Core has mcp[cli], sqlalchemy, sqlglot, toon-format only. Dialect drivers in optional extras. | ✓ |
| Core = mssql drivers included | Keep pyodbc+azure-identity in core deps. Only databricks is optional. | |
| You decide | Claude picks based on cleanest packaging story. | |

**User's choice:** Core = zero DB drivers

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy import with custom error message | Each dialect's create_engine catches ImportError, raises clear install instruction. | ✓ |
| Registry-time check | Check for dialect dependencies when registering. | |

**User's choice:** Lazy import with custom error message
**Notes:** Error at connection time, not at module import

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add [all] extra | pip install dbmcp[all] gets mssql+databricks+examples. | ✓ |
| No, keep extras separate | Only [mssql], [databricks], [examples]. | |

**User's choice:** Yes, add [all] extra

---

## Registry Fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit only — dialect='generic' required | GenericDialect only activates for explicit dialect='generic' in TOML. Unknown names still error. | ✓ (TOML path) |
| Auto-fallback for unknown names | get_dialect('postgres') returns GenericDialect instead of erroring. | |

**User's choice:** Explicit only for TOML config path

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — unknown URL schemes use GenericDialect | Auto-detect, warn-but-proceed for unknown schemes. | ✓ (URL path) |
| No — error on unknown URL schemes | Only allow mapped URL schemes. | |

**User's choice:** Yes, but with warning log (not silent)
**Notes:** User clarified split behavior: TOML requires known dialect (error on unknown), URL auto-detects and warns on unknown schemes but proceeds via GenericDialect.

---

## Claude's Discretion

- D-14: URL-scheme-to-dialect mapping structure and placement
- D-15: GenericDialect create_engine pool configuration and kwargs
- D-16: connect_database internal routing logic refactoring

## Deferred Ideas

None — discussion stayed within phase scope
