# Phase 0 Research: Hardening & Cleanup Pass

All findings re-verified against current `main` (HEAD `6ff34d8`) on 2026-06-01. The spec's
core assumption — "file:line references will be re-verified; code may have shifted" — paid off
immediately: the largest known item (IN-02/03/04) is already mostly refactored.

---

## D-01 — WR-05 Option B: how does the cross-catalog reflector return a `TypeEngine`?

**Decision**: In `ColumnStatsCollector.get_column_data_type` (`column_stats.py:193-228`), the
cross-catalog Databricks branch currently returns the raw DESCRIBE-TABLE **string** from
`_reflect_catalog_columns()` (e.g. `"int"`, `"string"`, `"decimal(10,2)"`). Convert that
string to a SQLAlchemy `TypeEngine` so the `isinstance(type_info, sa_types.TypeEngine)` gate
in both `get_columns_info` (line 625) and `get_column_statistics` (line 513) passes. Use the
Databricks SQLAlchemy dialect's own type compiler/registry to parse the string into a type
object; fall back to `sa_types.NullType()` (NOT a string) for an unrecognized type so the
gate's behavior is well-defined and the result contract is preserved.

**Rationale**:
- The downstream consumers already accept a `TypeEngine` and only need it for
  `_get_type_category` (numeric/datetime/string/other classification) and `str(type_obj)` for
  the `data_type` response field. `_get_type_category` (line 230) already handles both
  `TypeEngine` and string inputs, so the result contract (`data_type` string, category-driven
  stats shape) is preserved either way — the only change is the fast path now *fires*.
- Returning `NullType()` for unknowns keeps `isinstance(..., TypeEngine)` **True** (NullType IS
  a TypeEngine), which means even an unmappable type takes the fast path and lands in the
  "other" category — matching what the default-catalog Inspector path already does for unknown
  types (it returns `NullType()` at line 211). Symmetry across the two paths.
- `databricks.sqlalchemy._types` exposes the dialect's custom types
  (`TIMESTAMP_NTZ`, `TINYINT`, `DatabricksStringType`, …); the install already depends on
  `databricks-sqlalchemy`, so no new dependency.

**Alternatives considered**:
- *Option A (gate the fast path off as default-catalog-only)* — rejected by the user during
  clarify: cross-catalog is the common, costly path in their Databricks usage, so the dead
  fast path is a real latency cost, not a nice-to-have.
- *Hand-rolled string→category map bypassing TypeEngine* — rejected: it would leave
  `data_type` as a bare string and duplicate the classification knowledge that
  `_get_type_category`'s isinstance ladder already encodes (DRY). The `data_type` response
  field would also drift from the default-catalog path's `str(TypeEngine)` formatting.

**Verification hook (SC-008)**: live `get_column_info` against a cross-catalog Databricks
table must return the *same response keys/shape* it returns today via Tier-2, now sourced
from precomputed stats. Capture before/after for one numeric + one string column.

**Open implementation note**: confirm exactly which parsing entry point the Databricks
dialect offers for "type string → TypeEngine" (a `type_compiler`/`ischema_names`-style map is
not exposed at the class level — `DatabricksDialect.ischema_names` does not exist). The
tasks phase will pin the exact call (candidate: reuse the dialect's reflection type mapping
or a small explicit dict keyed on the DESCRIBE token, since the set of Databricks scalar type
tokens is small and stable). This is the one genuinely new code path in the phase and gets a
dedicated red-green test plus live validation.

---

## D-02 — TD-02: URL-mode probe engine `ca_bundle` inheritance

**Decision**: In `connect_with_url` (`connection.py:364-378`), the Databricks
catalog-required branch calls `_require_databricks_catalog(...)` **without** `ca_bundle`. The
helper already accepts `ca_bundle` (signature at line 515) and the named-config path already
forwards it (line 618-625). Fix = extract `ca_bundle` from the parsed URL kwargs
(`dialect._kwargs_from_url(sqlalchemy_url, {})` already returns it — `databricks.py:241-243`
copies `?ca_bundle=` into `new_kwargs`) and pass it into the helper call, exactly as the
config path does.

**Rationale**: Pure symmetry fix — the helper, the config path, and `_kwargs_from_url` all
already handle `ca_bundle`; only the URL-mode call site drops it. ~3 LOC + one unit test
asserting the probe engine receives `ca_bundle` when the URL carries `?ca_bundle=`. The
`_tls_trusted_ca_file` mentioned in TD-02 is derived *inside* `create_engine` from `ca_bundle`
(line 328-332), so forwarding `ca_bundle` is sufficient — no separate `_tls_trusted_ca_file`
threading needed. **This corrects the spec's FR-003 wording**, which over-specified by listing
both; the ledger will note this as a scope clarification, not a deviation.

**Live validation**: deferred to follow-up UAT (needs the corp-MITM TLS network) per FR-017 —
the only sanctioned live-deferral in the phase.

---

## D-03 — TD-01: regression tests only, no production change

**Decision**: Add two tests to `tests/unit/test_connect_with_config_databricks.py`
(reuse `_make_engine_spy`, line 27): (1) `catalog="${DBX_CATALOG}"` /
`schema_name="${DBX_SCHEMA}"` resolve from env into captured engine kwargs
(exercises `resolve_env_vars` at `connection.py:579-580`); (2) a `SQLAlchemyError` from
`dialect.create_engine` is wrapped in `ConnectionError` with the host string present
(`connection.py:629-636`).

**Rationale**: Both code paths are correct and already shipped; these close coverage gaps the
existing literal-string tests never exercise. The spy fixture already exists. Pure red-green
on test-only additions (the "red" is the coverage gap; tests pass once written against correct
code — verify they would fail if the production lines were deleted, per the TD-01 note).

---

## D-04 — IN-02/03/04: already refactored — FR-006 collapses

**Decision**: The duplicated cross-catalog existence-check scaffolding TD-03 describes as
copy-pasted across three tools **no longer exists as duplication**. `analysis_tools.py`
already has module-level `_is_cross_catalog` (line 26) and `_check_table_exists` (line 41),
and all three tools (`get_column_info` line 206, `find_pk_candidates` line 314,
`find_fk_candidates` line 441) call the shared helper. The "table not found" message is
already unified inside `_check_table_exists` (one template per branch). The lazy
`MetadataService` import (IN-02) is already hoisted to a single site inside the helper
(line 49).

**Consequence for FR-006**: reduces to (a) **verify** no residual inline duplication remains
across the tools (and inside `PKDiscovery`/`FKCandidateSearch`/`ColumnStatsCollector` per the
original IN-03 note), recording the verification in the ledger; (b) any *remaining* divergence
(e.g. the two not-found message templates `'schema.table' not found` vs
`'table' not found in schema 'schema'` still differ between cross-catalog and default
branches — IN-04's actual residue) is dispositioned: unify if it is a one-line local change,
else log. This is a `fixed`/`verified` ledger entry, not a large refactor.

**Rationale**: Honesty — the spec already assumed line refs would shift; this is the concrete
payoff. Re-doing an existing refactor would violate YAGNI and risk regressions for no gain.

---

## D-05 — IN-01: `list_tables` row-shape assertion

**Decision**: `CatalogAwareReflector.list_tables` (`_sql.py:178`) ends with
`return [row[1] if len(row) > 1 else row[0] for row in rows]`. The docstring states SHOW
TABLES returns `(database, tableName, isTemporary)` with `row[1]` the table name. The
`len(row) > 1` fallback to `row[0]` would silently return a *database name* as a table name
for a shape the docstring says never occurs. Fix = fail-fast on the unexpected shape (raise a
clear error) rather than silently mis-returning, OR document why the fallback is load-bearing.
Prefer fail-fast (Constitution IV: fail fast on programmer errors).

**Rationale**: Robustness/clarity. The same `len(row) > 1` defensive idiom appears in
`reflect_columns` (line 110) for `data_type` — review whether that one is genuinely defensive
(DESCRIBE TABLE rows can be short at section markers) vs misleading; disposition each
independently in the ledger.

---

## D-06 — WR-01 / WR-02: robustness fixes in `column_stats.py`

**Decision**:
- **WR-01** (`_try_describe_extended_stats`, `column_stats.py:437`): narrow
  `except Exception: return None` to `except SQLAlchemyError`. Distinguish "DESCRIBE EXTENDED
  genuinely unsupported / no stats" (return None → Tier-2 fallback, correct) from infra/auth
  errors that should propagate. A `ProgrammingError` for unsupported syntax is a subclass of
  `SQLAlchemyError`; verify Databricks raises a catchable SQLAlchemy error for "unsupported"
  so the fast-path-absent case still degrades gracefully rather than propagating.
- **WR-02** (`get_basic_stats` line 275-277; `get_numeric_stats` line 305; siblings): the
  `row[1] if row else 0` guards check `row` truthiness but then index `row[1]`/`row[2]`; a
  short row raises `IndexError` rather than falling back. Fix = trust the aggregate contract
  (a `SELECT COUNT(*), …` always returns a full-width single row) and drop the misleading
  guard, OR guard width explicitly. Trusting the contract is simpler and correct (an aggregate
  with no GROUP BY always returns exactly one full row); the `if not row` guard in
  `get_numeric_stats` (line 305) is dead for the same reason and gets the same treatment.

**Rationale**: Both are Constitution IV applications. WR-01 is flagged "promote to urgent if
it ever masks a real incident" — landing it removes a silent-failure class. Each is a small
local change with a red-green test (WR-01: assert a non-DESCRIBE error propagates; WR-02:
assert correct stats without the spurious guard).

---

## D-07 — Sweep methodology (US2 `src/`, US3 `tests/`)

**Decision**: Sequential, module-by-module review recorded in one `findings.md` ledger with a
`SRC-NN` prefix for `src/` findings and a `TST-NN` prefix for `tests/` findings (distinct
sections, per FR-010/FR-012). Each finding: ID, location (`file:line`), severity
(critical/warning/info, matching the 15.1-REVIEW.md scale), description, and **disposition**
(`fixed` w/ commit+test ref, `verified` w/ note, or `logged` w/ TECH-DEBT/BACKLOG ID). Triage
bar (from clarify Q1): correctness bugs fixed always; simplifications fixed only when local to
TD-01/02/03 code being touched; larger refactors logged.

**Rationale**: Follows the existing 15.1-REVIEW.md precedent the team already reads, making
SC-002 ("100% of modules reviewed, 100% of findings dispositioned") mechanically verifiable —
no module absent from the ledger, no finding without a disposition. Single ledger (not
per-module files) keeps the artifact greppable and the disposition audit one-pass.

**Coverage tracking**: the ledger opens with a checklist of every `src/` module (from
`find src -name '*.py'`) so an unreviewed module is visibly unchecked — this is the SC-002
evidence.

**Sequencing**: `src/` sweep AFTER the known fixes land (so the sweep reviews post-fix code and
doesn't re-flag what's being fixed); `tests/` sweep LAST (P3) because P1/P2 changes add/remove
tests and the suite must stabilize first (spec US3 rationale).

---

## Summary of decisions

| ID | Decision | New code? | Live-validated? |
|----|----------|-----------|-----------------|
| D-01 | WR-05 Option B: cross-catalog reflector → `TypeEngine` (NullType fallback) | Yes (type parse) | **Yes (SC-008)** |
| D-02 | TD-02: forward `ca_bundle` into URL-mode probe call | ~3 LOC | Deferred (corp-MITM UAT) |
| D-03 | TD-01: 2 regression tests, reuse `_make_engine_spy` | Test-only | N/A |
| D-04 | IN-02/03/04 already refactored → FR-006 = verify + dispo residue | No / tiny | N/A |
| D-05 | IN-01: fail-fast on `list_tables` row shape | Small | Databricks live |
| D-06 | WR-01 narrow except; WR-02 fix row guards | Small | Databricks live |
| D-07 | Single `findings.md` ledger, SRC-/TST- prefixes, module checklist | Doc | N/A |

No NEEDS CLARIFICATION markers remain. One implementation detail (the exact Databricks
type-string→TypeEngine entry point, D-01) is pinned during `/speckit.tasks`.
