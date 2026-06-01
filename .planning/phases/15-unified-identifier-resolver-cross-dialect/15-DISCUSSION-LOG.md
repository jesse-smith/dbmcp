# Phase 15: Unified identifier resolver - Discussion Log

> **Audit trail only.** Not consumed by downstream agents. Decisions live in CONTEXT.md.

**Date:** 2026-05-28
**Phase:** 15-unified-identifier-resolver-cross-dialect
**Mode:** discuss (--all)
**Areas:** Resolver architecture · Parsing & conflict rules · Catalog gate & default schema · SC4 sweep + tests + roadmap

## Resolver architecture
- **Home:** Standalone `src/db/identifiers.py` + dialect props (vs method on DialectStrategy / MetadataService) → **standalone**. Shared logic DRY, dialect facts on dialect.
- **Return type:** Frozen dataclass `ResolvedIdentifier` (vs plain tuple) → **dataclass**.
- **Invocation:** At each `@mcp.tool` boundary (vs inside MetadataService) → **boundary**.

## Parsing & conflict rules
- **Conflict rule:** Error on disagreement only (vs error on any double-spec) → **disagreement only** (matches IDENT-04 wording).
- **Error shape:** `ValueError` + named message (vs new ConfigurationError) → **ValueError** (Phase 14 deferred error-class cleanup).
- **Quoting:** Split-on-unquoted-dots vs naive vs defer → **defer to research** (check sqlglot first).

## Catalog gate & default schema
- **Inconsistency surfaced:** existing 3 tools say catalog "ignored" on non-DBX; IDENT-05/06 require error. Resolved → **error everywhere, unify all 5** (vs error-only-on-2-new / defer). Flagged backward-incompatible.
- **default_schema:** MSSQL=dbo, DBX=session(None), generic=None (vs DBX literal 'default') → **session/None** (no hardcoded name).
- **No-schema path:** Pass None through to SQLAlchemy (vs error if required) → **pass None**.

## SC4 sweep + tests + roadmap
- **dbo sweep:** Tools + service layer all dbo defaults (vs tool signatures only) → **tools + service**.
- **Test matrix:** Resolver unit matrix + thin per-tool checks (vs full matrix ×5) → **unit + thin**.
- **Roadmap fix:** Correct ROADMAP.md `src/tools/`→`src/mcp_server/` in addition to CONTEXT.md (vs note in CONTEXT only) → **fix both**.

## Deferred
- ConfigurationError taxonomy (Phase 14 tech-debt pass); DISC-01 list_catalogs; row-limit/sample_size naming.
