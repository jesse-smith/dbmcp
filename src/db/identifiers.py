"""Cross-dialect identifier resolution.

A single dialect-agnostic layer that parses, validates, and normalizes
``table_name`` / ``schema_name`` / ``catalog`` so the namespace-aware MCP tools
stop interpreting identifier structure themselves. Pure business logic -- no
side effects, no database connection required.

Dialect facts (``sqlglot_dialect``, ``max_identifier_depth``, ``default_schema``)
come from the DialectStrategy properties. Depth is measured by ``len(parts)``,
NOT by ``Table.name/db/catalog`` -- ``to_table("a.b.c.d")`` does not raise; it
folds the extra segment and the attributes silently report only three slots
(RESEARCH Pitfall 1). Counting ``.parts`` is the only correct depth check.

This module is NOT a SQL sanitizer. ``to_table("a; DROP TABLE b")`` parses as
one literal identifier and is returned verbatim; the existing
``dialect.quote_identifier`` path downstream remains the injection defense.
"""

from dataclasses import dataclass

import sqlglot

# Shared catalog-gate message template (D-05 phrasing). Module-level so that
# table_name-less tools (list_schemas, find_pk/fk_candidates) reuse the exact
# wording via _assert_catalog_allowed instead of duplicating it.
CATALOG_GATE_MESSAGE = (
    "catalog is not supported for the '{name}' dialect "
    "(max identifier depth {depth}; catalog requires depth 3)"
)


@dataclass(frozen=True)
class ResolvedIdentifier:
    """A fully resolved, dialect-validated identifier (D-02).

    All fields are required. ``catalog`` and ``schema`` may be None when the
    dialect does not supply or require them; ``table`` is always present.
    """

    catalog: str | None
    schema: str | None
    table: str


def _assert_catalog_allowed(catalog: str | None, dialect) -> None:
    """Raise ValueError if a catalog is supplied to a dialect that cannot use it.

    Shared by ``resolve_identifier`` and the table_name-less tools
    (list_schemas, find_pk_candidates, find_fk_candidates). No-op when
    ``catalog`` is falsy or the dialect supports three-part identifiers.
    """
    if catalog and dialect.max_identifier_depth < 3:
        raise ValueError(
            CATALOG_GATE_MESSAGE.format(
                name=dialect.name, depth=dialect.max_identifier_depth
            )
        )


def resolve_identifier(
    table_name: str,
    schema_name: str | None,
    catalog: str | None,
    dialect,
) -> ResolvedIdentifier:
    """Parse, validate, and normalize an identifier for the given dialect.

    Args:
        table_name: Possibly-dotted identifier (e.g. ``"sales.orders"``).
        schema_name: Explicit schema parameter, or None.
        catalog: Explicit catalog parameter, or None.
        dialect: A DialectStrategy exposing ``sqlglot_dialect``,
            ``max_identifier_depth``, ``default_schema``, and ``name``.

    Returns:
        A frozen ResolvedIdentifier.

    Raises:
        ValueError: on malformed input, over-depth identifiers, a catalog
            supplied to a shallow dialect, or a conflict between a parsed
            segment and the matching explicit parameter.
    """
    # 1. Parse. Normalize sqlglot.ParseError -> ValueError (A1) so it maps
    #    cleanly through the existing tool-boundary `except ValueError` path.
    try:
        parsed = sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)
    except sqlglot.ParseError as e:
        raise ValueError(f"Malformed table_name {table_name!r}: {e}") from e

    # 2. Decompose into unquoted parts. `.name` is the unquoted identifier text.
    parts = [p.name for p in parsed.parts]

    # 3. Catalog gate (D-07) -- reuse the shared helper; must run before the
    #    depth check so a catalog on a shallow dialect reports the gate message.
    _assert_catalog_allowed(catalog, dialect)

    # 4. Depth check via len(parts) -- the Pitfall-1 trap. Attributes lie; the
    #    parts list does not.
    if len(parts) > dialect.max_identifier_depth:
        raise ValueError(
            f"Identifier {table_name!r} has {len(parts)} parts; the "
            f"'{dialect.name}' dialect allows at most "
            f"{dialect.max_identifier_depth} parts: {parts}"
        )

    # 5. Right-to-left map: table is always the last part.
    table = parts[-1]
    parsed_schema = parts[-2] if len(parts) >= 2 else None
    parsed_catalog = parts[-3] if len(parts) >= 3 else None

    # 6. Conflict detection (D-04) -- disagreement only; redundant-but-consistent
    #    input is allowed.
    if parsed_schema and schema_name and parsed_schema != schema_name:
        raise ValueError(
            f"Conflicting schema: table_name implies '{parsed_schema}' "
            f"but schema_name='{schema_name}'"
        )
    if parsed_catalog and catalog and parsed_catalog != catalog:
        raise ValueError(
            f"Conflicting catalog: table_name implies '{parsed_catalog}' "
            f"but catalog='{catalog}'"
        )

    # 7. Fill: parsed segment wins, then explicit param, then dialect default.
    final_schema = parsed_schema or schema_name or dialect.default_schema
    final_catalog = parsed_catalog or catalog

    return ResolvedIdentifier(catalog=final_catalog, schema=final_schema, table=table)
