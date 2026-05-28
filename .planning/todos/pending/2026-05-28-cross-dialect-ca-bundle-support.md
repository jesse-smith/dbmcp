---
slug: cross-dialect-ca-bundle-support
category: database
priority: low
created: 2026-05-28
trigger: "Databricks ca_bundle config field shipped (260528-gsk). MSSQL/generic don't have this hook yet — promote to dialect-protocol level when a second dialect runs into a corp-MITM gateway."
---

# Promote ca_bundle to ConnectionConfig protocol (Option 3)

## Context
Quick task 260528-gsk shipped Option 2 from `.planning/debug/resolved/databricks-tls-self-signed.md`:
a Databricks-only `ca_bundle` field + `DBMCP_CA_BUNDLE` env fallback. MSSQL and generic
dialects do not have an equivalent hook. User confirmed MSSQL endpoint is not currently
behind the corp gateway, so this is non-urgent.

## Trigger to action
File this as the work-to-do when ANY of:
- A second dialect (MSSQL, generic, or future) hits a corp-MITM SSLCertVerificationError.
- A user asks for a unified TLS-trust-bundle config across dialects.
- The dialect protocol is being refactored for any other reason (ride that change).

## Scope
- Promote `ca_bundle: str = ""` to a base `ConnectionConfig` protocol/dataclass field
  (or a mixin) that all dialect configs inherit.
- Each dialect's `create_engine` consumes it via the dialect-appropriate connect_arg
  (`_tls_trusted_ca_file` for Databricks; pyodbc/MSSQL has its own; SQLAlchemy generic
  varies by driver — research each).
- Keep `DBMCP_CA_BUNDLE` env fallback semantics; document precedence consistently.
- One README section for all dialects, not per-dialect.

## Out of scope
- Per-dialect TLS knobs beyond ca_bundle (cipher suites, cert pinning, etc.).
