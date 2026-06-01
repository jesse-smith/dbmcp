# Phase 14: Connect-time hardening (Databricks) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-05-11
**Phase:** 14-connect-time-hardening-databricks
**Mode:** discuss
**Areas discussed:** Catalog-missing detection, Error shape for IDENT-01, SHOW CATALOGS helper placement, Scope of _list_databricks_catalogs removal

---

## Area 1 — Catalog-missing detection

**Q: Where should the catalog-required check live?**
- Options: In `DatabricksDialect.create_engine` (rec) / at `connect_with_url` + `connect_with_config` / split across config and URL paths
- **Selected:** In `DatabricksDialect.create_engine`. Dialect owns its rules; one check covers both paths.

**Q: Should the dialect stop defaulting catalog to `"main"`?**
- Options: Remove the default entirely (rec) / keep with opt-in flag
- **Selected:** Remove entirely. The silent `"main"` default is exactly the class of bug IDENT-01 removes.

---

## Area 2 — Error shape for IDENT-01

**Q: What should the error look like when SHOW CATALOGS succeeds?**
- Options: All catalogs sorted (rec) / first 20 + count / just names no guidance
- **Selected:** First 20 catalogs + count. Bounds message size against pathological workspaces.

**Q: What if SHOW CATALOGS itself fails?**
- Options: Raise with original chained (rec) / swallow with generic note
- **Selected:** Raise with original chained via `raise ... from exc`. User sees both problems at once.

**Q: Which exception type should this raise?**
- User initially asked: "How is incomplete/incorrect config handled currently?"
- Claude checked the codebase and found the original recommendation (`ConfigurationError`) was wrong — no such class exists. Actual patterns: `ValueError` for presence/shape (dialect level), custom `ConnectionError` for connect-time IO failures.
- User asked: "Does `create_engine` currently do any validation?" Claude confirmed: yes, presence validation only, all `ValueError`. `create_engine` is currently IO-free.
- This sharpened the tradeoff: SHOW CATALOGS is IO; putting it in `create_engine` would break its pure-validation shape.
- **Selected (by user):** Connect-layer pattern. `create_engine` does presence check → raises `ValueError`. Connect layer catches that, runs SHOW CATALOGS, re-raises as `ConnectionError` with enriched message.
- User quote: *"create_engine should check existence, connection should check whether that's a legitimate catalog. So the IO part should live at connection time."*

---

## Area 3 — SHOW CATALOGS helper placement

**Q: Where should the SHOW CATALOGS helper live?**
- Options: Method on `DatabricksDialect` (rec) / module-level function in `databricks.py` / reuse renamed helper in `metadata.py`
- **Selected:** Method on `DatabricksDialect`. Dialect-owned SQL stays with the dialect; DISC-01's future `list_catalogs` tool will reuse it.

---

## Area 4 — Scope of `_list_databricks_catalogs` removal

**Q: How much of the old fallback path should be deleted?**
- User clarification requested: "What's the tradeoff for removing the `default_catalog` function as well?"
- Claude analyzed: function body is `try: return self.engine.url.query.get("catalog", "main") except AttributeError: return "main"`. Both `"main"` fallbacks are dead post-IDENT-01. Real question is whether to keep a named wrapper around a one-liner.
- Claude recommendation: keep it, but strip the fallbacks (body becomes `return self.engine.url.query["catalog"]`, letting `KeyError` propagate as a loud invariant-break).
- User agreed. Follow-up question: "`'default' catalog might read as akin to 'default' for e.g. SQL Server, but in databricks that doesn't exist. What is it actually reading?"
- Claude explained: it reads `engine.url.query["catalog"]` — the catalog baked in at connect time. Nothing session-level. Confirmed the naming is MSSQL-flavored and misleading for Databricks.
- User asked about `_config_catalog`. Claude flagged that "config" collides with `DatabricksConnectionConfig` (class name) and would wrongly imply the catalog came from that class even on URL-based paths. Suggested `_engine_catalog` or `_connected_catalog`.
- **Selected (by user):** Rename to `_engine_catalog`. "That's clearest to me."

**Q: Should `list_schemas` still accept an optional `catalog=` parameter?**
- Options: Keep it (rec) / remove it
- **Selected:** Keep it. Still useful for cross-catalog exploration post-connect; consistent with Phase 15 direction.

**Q: IDENT-02 regression test — what asserts the pre-IDENT-01 failure mode is gone?**
- Options: Spy and assert no SHOW CATALOGS call (rec) / assert schemas aren't catalog names / both
- **Selected:** Spy on `engine.execute` and assert no `SHOW CATALOGS` issued during `list_schemas` on Databricks.

---

## Claude's Discretion
- Exact test file layout (one file vs split) — planner/executor call.
- Error-message phrasing within the D-05 template.
- Structural placement of `_require_databricks_catalog` (module fn, ConnectionManager method, or dialect helper).

## Deferred Ideas
- Broader error-class inconsistency (`ValueError` / custom `ConnectionError` / no `ConfigurationError`) — tech-debt pass, not v2.1.
- MSSQL-flavored vocabulary audit across cross-dialect code paths — tech-debt pass.
- DISC-01 cross-dialect catalog enumeration tool — already in roadmap backlog; reuses Phase 14's `DatabricksDialect.list_catalogs`.
- Phase 15 identifier resolver (IDENT-03 through IDENT-07) — explicit dependency on Phase 14.

---

*Discussion log for Phase 14 — 2026-05-11*
