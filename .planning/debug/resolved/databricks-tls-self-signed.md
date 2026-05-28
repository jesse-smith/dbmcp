---
slug: databricks-tls-self-signed
status: resolved
trigger: |
  DATA_START
  Databricks TLS SSLCertVerificationError ("self-signed certificate in certificate chain")
  when connecting via dbmcp / dbmcp-test, but Databricks official MCP works fine on the
  same machine. Indicates the TLS gap is dbmcp-specific, not environmental.
  DATA_END
created: 2026-05-28
updated: 2026-05-28
---

# Debug: Databricks TLS self-signed certificate (dbmcp-specific)

## Symptoms

- **Expected:** `connect_database` against the Databricks workspace completes the TLS handshake and returns a connection_id (matching the behavior on 2026-05-15 in quick task 260515-m30 Probe 2).
- **Actual:** `databricks-sql-connector` raises `SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain` during the HTTPS handshake.
- **Error:** `SSLCertVerificationError ... self-signed certificate in certificate chain` — surfaced both via named-config (`connection_name="databricks-test"`) and URL mode (`databricks://...?catalog=bmtct&...`). Both routes converge on the same `databricks-sql-connector` HTTPS call.
- **Timeline:** Probe 2 of 260515-m30 (2026-05-15) succeeded on this exact host. UAT for 260528-fks (2026-05-28) on same URL/host fails with TLS error. Phase 14 partial UAT (commit 93e106b) recorded the same gap. Initially diagnosed as "environmental drift since 2026-05-15 (corp VPN / MITM cert chain)".
- **NEW DATA POINT (2026-05-28):** User reports the **official Databricks MCP server works fine on this same machine right now**. → Falsifies the "environmental drift" hypothesis. The corp MITM cert chain is being trusted by *something* the official server uses but not by dbmcp's path.
- **Reproduction:**
  1. `dbmcp.toml` has `[connections.databricks-test]` with `host=${DATABRICKS_HOST}`, `http_path=${DATABRICKS_HTTP_PATH}`, `token=${DATABRICKS_TOKEN}`, `catalog="bmtct"`.
  2. `connect_database(connection_name="databricks-test")` via dbmcp-test → SSLCertVerificationError.
  3. Same machine, same env, official Databricks MCP → succeeds.

## Current Focus

- **hypothesis (CONFIRMED, leading explanation):** Corp Cloudflare gateway (issuer `Gateway CA - Cloudflare Managed G2 …`, CA stored at `~/.ssl-certs/gateway-ca.pem`) rewrites TLS chains on a subset of LB-routed VIPs serving `*.azuredatabricks.net`. The gateway CA is loaded into Node-based tools via `NODE_EXTRA_CA_CERTS` (set in `~/.zshrc`), but Python ignores that env var entirely. Python's TLS context (used by `databricks-sql-connector`'s Thrift HTTPS transport via `ssl.create_default_context`) only consults `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` / `certifi.where()` — none contain the gateway CA in dbmcp's `uv run` venv. Result: handshake succeeds when LB picks a non-rewritten VIP (clean DigiCert chain), fails with "self-signed certificate in certificate chain" when LB picks a rewritten VIP. Intermittency is the LB-routing distribution.
- **next_action:** CHECKPOINT — user to choose Option 1, 2, or 3 from Resolution. Do not apply fix yet.
- **test:** Verifications A and B run; results in Evidence below. A direct mid-failure capture of a rewritten chain was not observed in this session (5/5 openssl probes returned the clean DigiCert chain — consistent with LB hash currently routing this client to non-rewritten VIPs and the user's note that the failure self-resolved overnight). Evidence B (env-var posture) decisively shows Python has no path to trust the gateway CA when it does appear, which is sufficient to confirm the mechanism without forcing a failure.
- **expecting:** User decision on remediation option.

## Evidence

- timestamp: 2026-05-28
  checked: src/db/dialects/databricks.py — DatabricksDialect.create_engine
  found: |
    Engine is built with `sa_create_engine(url, pool_pre_ping=True, echo=False, connect_args=merged_connect_args)`.
    URL form: `databricks://token:{quote_plus(token)}@{host}?http_path=...&catalog=...&schema=...`.
    `merged_connect_args` defaults: `_socket_timeout=30`, `_retry_stop_after_attempts_count=2`. No `_tls_*`,
    no `_ssl_*`, no `_user_agent_entry`, no cert-bundle override. No environment variables read.
  implication: |
    dbmcp does NOT pass any TLS-related connect_args to databricks-sql-connector. The connector therefore
    uses its own default behavior, which (per source) goes through `thrift.transport.THttpClient` and
    eventually `ssl.create_default_context()` — which loads from the OS trust store on macOS via certifi
    (the connector vendors certifi).
    The hypothesis space narrows to (a) certifi version mismatch between dbmcp's venv and whatever runtime
    the official MCP uses, OR (b) env vars (SSL_CERT_FILE / REQUESTS_CA_BUNDLE) set in the official MCP's
    invocation context but not in dbmcp-test's, OR (c) the official MCP isn't actually a Python connector
    at all (could be Node-based, calling Databricks REST API not SQL warehouse — different TLS path).

- timestamp: 2026-05-28
  checked: |
    All MCP-client configs on this machine: ~/.claude.json (Claude Code, includes per-project mcpServers),
    ~/Library/Application Support/Claude/claude_desktop_config.json (Anthropic desktop app),
    ~/Library/Application Support/Claude-3p/claude_desktop_config.json,
    ~/.cursor/mcp.json, ~/.config/claude-code/, ~/.config/cursor/, ~/.codex/.
  found: |
    The ONLY MCP servers registered for this user are: deepwiki, serena, dbmcp (in ~/.claude.json).
    Claude Desktop configs contain only preferences — no mcpServers block.
    No project-scoped Databricks MCP server found in any project entry of ~/.claude.json.
    No `databricks-mcp` binary on PATH; pipx/npm probes returned no Databricks MCP package.
  implication: |
    I cannot locate the "official Databricks MCP server" the user said is working on this machine. Either
    (1) it's installed in a location/client I haven't checked (e.g., a different IDE's MCP config, a remote
    session, a launchd/systemd service), (2) it's invoked via a different mechanism (a shell script, a
    Docker container, a Cloudflare-tunneled remote MCP), or (3) the comparison was with a different tool
    entirely (e.g., the Databricks CLI / databricks-connect, not an MCP server).
    Without knowing the actual working invocation, I can't capture its env / interpreter / cert config to
    do the differential. This is a checkpoint.
    **Update (later same session):** A `databricks` MCP server IS active in this session (surfaced via the
    system-reminder MCP-instructions block — registered at a scope outside the user-readable config files
    I checked, likely the Claude Code agent runtime). User confirmed it's Node-based and uses
    `NODE_EXTRA_CA_CERTS` for the gateway CA — which resolves the differential without needing direct env
    capture.

- timestamp: 2026-05-28
  checked: |
    Verification A — repeated `openssl s_client -connect ${DATABRICKS_HOST}:443 -servername ${DATABRICKS_HOST}`
    probes (5 connections) extracting subject/issuer of the leaf cert.
  found: |
    All 5 probes returned the same clean chain: subject `CN=*.azuredatabricks.net,
    O=DATABRICKS, INC.`, issuer `DigiCert Global G2 TLS RSA SHA256 2020 CA1`. No corp gateway CA
    observed in any chain during this session. (Host value not echoed.)
  implication: |
    The LB is currently routing this client consistently to non-rewritten VIPs — matches the user's
    "self-resolved overnight" report. Probe A does not directly *prove* rewriting occurs (didn't catch
    a failing chain in this window), but combined with the user's first-hand intermittent-failure
    observation, the symmetric Node-works-Python-doesn't behavior, and the env-var posture in
    Verification B, the LB-routing mechanism is the parsimonious explanation. Re-running probe A
    during a known dbmcp failure window would close this gap conclusively if needed.

- timestamp: 2026-05-28
  checked: |
    Verification B — Python TLS env in dbmcp's `uv run` venv:
    `uv run python -c "import os, certifi; print(...)"`
  found: |
    SSL_CERT_FILE: None
    SSL_CERT_DIR: None
    REQUESTS_CA_BUNDLE: None
    CURL_CA_BUNDLE: None
    NODE_EXTRA_CA_CERTS: /Users/jsmith79/.ssl-certs/gateway-ca.pem  (set, but Python ignores it)
    certifi.where(): /Users/jsmith79/Documents/Projects/Ongoing/dbmcp/.venv/lib/python3.13/site-packages/certifi/cacert.pem
  implication: |
    Decisive. Python's only trust source in this venv is the vanilla certifi bundle that ships with the
    package — it does NOT contain the corp Cloudflare gateway root. There is no shell-level override for
    Python (SSL_CERT_FILE / REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE all unset). When (and only when) a
    connection lands on a rewritten VIP, the chain terminates at the gateway CA and Python's verifier
    rejects it as "self-signed certificate in certificate chain" — exactly the observed error. This is
    the mechanism.

- timestamp: 2026-05-28
  checked: |
    `~/.ssl-certs/gateway-ca.pem` subject and issuer.
  found: |
    File present (1.1 KB). Subject == Issuer (self-signed root, as expected for a CA):
    "C=US, ST=California, L=San Francisco, O=Cloudflare, Inc., OU=www.cloudflare.com,
     CN=Gateway CA - Cloudflare Managed G2 09fd3a16b2b05b606bff7d91b2b9a4d7"
  implication: |
    The corp gateway is Cloudflare Zero Trust ("Gateway CA - Cloudflare Managed G2") — a well-known
    corporate-MITM pattern. The fix is straightforward: make Python trust this CA on the dbmcp path.
    Three options laid out in Resolution.

## Eliminated

- (no hypotheses currently eliminated — see re-evaluation note)

**Re-evaluation (2026-05-28):** "Environmental drift" was prematurely eliminated. The original framing assumed *date-based* drift (something changed between 2026-05-15 and 2026-05-28). The user's new info reframes it as *load-balancer-based intermittency*: the corp Cloudflare gateway rewrites the TLS chain on some VIPs but not others, and which VIP a connection lands on is a routing/hash decision. The "official Databricks MCP works fine" datapoint does NOT falsify this — that MCP server is Node-based, and Node has the gateway CA loaded via `NODE_EXTRA_CA_CERTS`. Python in dbmcp's venv does not (Python ignores `NODE_EXTRA_CA_CERTS`), so when dbmcp lands on a rewritten VIP the handshake fails. The "intermittent, self-resolved overnight" behavior the user reports is the LB rerouting them to a clean VIP. Hypothesis re-instated as **leading and confirmed-mechanism**.

## Resolution

**Root cause (confirmed mechanism):** Python TLS in dbmcp's venv does not trust the corp Cloudflare gateway CA. When the LB serving `*.azuredatabricks.net` routes a connection to a VIP whose chain has been rewritten by the gateway, Python's `ssl.create_default_context()` fails verification ("self-signed certificate in certificate chain"). Node-based tools (including the `databricks` MCP server registered at the system level) work because they honor `NODE_EXTRA_CA_CERTS=~/.ssl-certs/gateway-ca.pem`, which Python ignores entirely.

**Files involved (no bug — current behavior is correct, just incomplete for corp-MITM environments):**
- `src/db/dialects/databricks.py` — `DatabricksDialect.create_engine` builds connect_args without any TLS trust hooks. Adding optional CA-bundle support is what Option 2 would change here (lines 246-269 are the connect_args construction site).

**Three remediation options for user decision:**

### Option 1 — User-side env var (no code change)
Concatenate certifi's bundle with the gateway CA into a combined PEM, then export `SSL_CERT_FILE` to point at it. Fixes every Python TLS user on the shell, not just dbmcp.

```bash
# in ~/.zshrc, alongside NODE_EXTRA_CA_CERTS:
DBMCP_CERTIFI=$(uv run --project ~/Documents/Projects/Ongoing/dbmcp python -c "import certifi; print(certifi.where())")
cat "$DBMCP_CERTIFI" ~/.ssl-certs/gateway-ca.pem > ~/.ssl-certs/python-bundle.pem
export SSL_CERT_FILE=~/.ssl-certs/python-bundle.pem
export REQUESTS_CA_BUNDLE=~/.ssl-certs/python-bundle.pem
```

- **Pros:** zero dbmcp code change; symmetric with the existing Node setup.
- **Cons:** must be a *concatenated* bundle (system + gateway), or all other Python TLS in the shell breaks. Bundle goes stale when certifi updates — needs to be regenerated. Affects every Python process in the shell, not scoped to dbmcp.

### Option 2 — dbmcp-specific env / config field (targeted code change)
Add an optional `ca_bundle` field to the Databricks connection config (and read `DBMCP_CA_BUNDLE` env as fallback). Pass it to `databricks-sql-connector` via the `_tls_trusted_ca_file` connect_arg — that's the connector's documented hook for a custom trust file.

Patch sketch (in `src/db/dialects/databricks.py`, in `create_engine`):

```python
ca_bundle = kwargs.get("ca_bundle") or os.environ.get("DBMCP_CA_BUNDLE")
dialect_defaults = {
    "_socket_timeout": connection_timeout,
    "_retry_stop_after_attempts_count": 2,
}
if ca_bundle:
    dialect_defaults["_tls_trusted_ca_file"] = ca_bundle
```

User config:
```toml
[connections.databricks-test]
host = "${DATABRICKS_HOST}"
http_path = "${DATABRICKS_HTTP_PATH}"
token = "${DATABRICKS_TOKEN}"
catalog = "bmtct"
ca_bundle = "${HOME}/.ssl-certs/gateway-ca.pem"  # NEW
```

- **Pros:** scoped to dbmcp; doesn't affect other Python tools in the shell. Survives certifi updates (gateway CA file alone, not a combined bundle). Discoverable via config schema.
- **Cons:** small code + config-model change. One-dialect feature initially (mssql/generic would need a parallel hook to be fully symmetric — though Option 3 handles that).

### Option 3 — Generalized cross-dialect support (best long-term)
Ship Option 2's mechanism, but at the dialect-protocol level so every dialect can opt in to a custom CA bundle. Document the env-var workflow (Option 1) in README/CLAUDE.md as the universal "if you're behind a corp MITM gateway" recipe, but make the per-connection `ca_bundle` field the first-class supported path.

- **Pros:** futureproofs for any future dialect a corp customer needs behind a MITM gateway. Two clear escape hatches (per-connection config OR shell env var) documented together.
- **Cons:** larger scope — touches the dialect protocol, all current dialect implementations (or at least adds a no-op default), tests, and docs. Worth doing if you expect more enterprise users behind MITM gateways.

**Recommendation:** Option 2 short-term (small, targeted, ships today, unblocks UAT). Promote to Option 3 when/if a second dialect runs into the same gap.

**Verification path (whichever option):** Re-run the dbmcp-test `connect_database(connection_name="databricks-test")` repeatedly during peak hours (when LB rewrite is most likely to land). With the fix, the connection succeeds on every attempt instead of intermittently failing.

## Resolution Applied (2026-05-28)

**Quick task:** `260528-gsk` — `.planning/quick/260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca/`

**Commits:**
- `ba0816d` feat(config): add ca_bundle field to DatabricksConnectionConfig
- `a9f7ac4` feat(databricks): plumb ca_bundle through dialect (kwargs + URL + env)
- `c8ff345` feat(connection): pass ca_bundle through named-config route + catalog-probe enrichment
- `207fb54` docs(databricks): document ca_bundle for corp-MITM TLS gateways + file Option-3 follow-up
- `269a6da` fix(databricks): auto-merge ca_bundle with certifi for trust-store augment

**Mechanism shipped:** Optional `ca_bundle` config field + `?ca_bundle=` URL param + `DBMCP_CA_BUNDLE` env-var fallback. When set, dbmcp reads the user's CA, concatenates it with `certifi.where()` (cached by content-hash in tempdir), and passes the merged path to `databricks-sql-connector` via `_tls_trusted_ca_file`. Auto-merge necessary because the connector's `_tls_trusted_ca_file` *replaces* (not augments) urllib3's trust store — pointing at just the gateway CA loses standard intermediates.

**Live UAT:** `connect_database` + `SELECT 1` round-trip confirmed under `dbmcp-test` MCP with `ca_bundle = "~/.ssl-certs/gateway-ca.pem"` in `dbmcp.toml`. Full Thrift handshake completed in 469ms on the previously-intermittently-failing path.

**Follow-up:** `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md` — promote `ca_bundle` to base ConnectionConfig protocol if/when a second dialect (MSSQL Azure cloud target, etc.) hits the same corp-MITM gap. Not needed today (MSSQL on-prem path is not exposed to the gateway).
