---
created: 2026-05-28T19:16:52.053Z
title: URL-mode probe engine should inherit ca_bundle for IDENT-01 enrichment
area: database
files:
  - src/db/connection.py
  - src/dialects/databricks.py
---

## Problem

When `connect_with_url` raises `ValueError("Databricks catalog is required")`, the
IDENT-01 enrichment helper builds a *probe engine* and runs `SHOW CATALOGS` to
populate the "Accessible catalogs: ..." list in the surfaced `ConnectionError`.

The probe engine is built fresh from the URL but does **not** inherit `ca_bundle`
from the URL query string. On corp-MITM TLS environments where `ca_bundle` is
required, the probe `SHOW CATALOGS` call fails with `SSLCertVerificationError`,
and enrichment falls into the D-06 fallback branch:

> `Databricks connection requires a catalog, and probing SHOW CATALOGS failed (MaxRetryError: ... self-signed certificate in certificate chain). Pass one via ?catalog= in the URL or catalog= in the config.`

The enrichment correctly fires (catalog-required invariant holds), but the user
never sees the actionable catalog list — even though the same workspace returns
22 catalogs over the named-config route which DOES carry ca_bundle through.

Asymmetry confirmed in Phase 14 UAT (2026-05-28, post-`260528-gsk`):
- Test 1 (named-config with `catalog="bmtct"`): `connection_id d9ce935f5dbb`, 22 schemas — ca_bundle from toml flows through.
- Test 2 (URL with `ca_bundle=~/.ssl-certs/gateway-ca.pem`, no catalog): probe-engine falls back to certifi → SSL fail → D-06 message.

## Solution

In the IDENT-01 enrichment helper (where the probe engine is constructed), parse
the inbound URL and forward `ca_bundle` (and likely `_tls_trusted_ca_file` after
the gsk auto-merge with certifi) to the probe engine's `connect_args`, exactly
like the user's real engine would receive them.

Should be a small, surgical fix in `src/db/connection.py` (or wherever the
probe-engine helper lives) — copy ca_bundle from the parsed URL params into the
probe engine kwargs.

Add a unit test that asserts the probe engine receives ca_bundle when the URL
carries one. Live UAT requires the corp-MITM environment.

## Out of scope

- Cross-dialect ca_bundle promotion (tracked separately in
  `2026-05-28-cross-dialect-ca-bundle-support.md`).
- Other URL-mode parameter inheritance gaps (assess if any others exist; if so,
  this todo can broaden to "URL-mode probe engine inherits all relevant connect
  params").
