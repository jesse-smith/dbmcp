"""Query validation against an AST-based denylist.

This module validates SQL queries by parsing them into an AST via sqlglot
and checking for denied operation types (DML, DDL, DCL, operational commands).
Pure functions — no side effects, no database connection required.
"""

import sqlglot
from sqlglot import exp

from src.logging_config import get_logger
from src.models.schema import (
    DenialCategory,
    DenialReason,
    ValidationResult,
)

# AST expression types mapped to denial categories
DENIED_TYPES: dict[type[exp.Expression], DenialCategory] = {
    # DML
    exp.Insert: DenialCategory.DML,
    exp.Update: DenialCategory.DML,
    exp.Delete: DenialCategory.DML,
    exp.Merge: DenialCategory.DML,
    # DDL
    exp.Create: DenialCategory.DDL,
    exp.Alter: DenialCategory.DDL,
    exp.Drop: DenialCategory.DDL,
    exp.TruncateTable: DenialCategory.DDL,
    # DCL
    exp.Grant: DenialCategory.DCL,
    exp.Revoke: DenialCategory.DCL,
    # Operational
    exp.Command: DenialCategory.OPERATIONAL,
}

# Control flow block types that may contain nested denied operations
_CONTROL_FLOW_TYPES = (exp.IfBlock, exp.WhileBlock)

# 22 known-safe SQL Server system stored procedures (lowercase, unqualified)
SAFE_PROCEDURES: frozenset[str] = frozenset({
    # Catalog/ODBC (12)
    "sp_column_privileges",
    "sp_columns",
    "sp_databases",
    "sp_fkeys",
    "sp_pkeys",
    "sp_server_info",
    "sp_special_columns",
    "sp_sproc_columns",
    "sp_statistics",
    "sp_stored_procedures",
    "sp_table_privileges",
    "sp_tables",
    # Object/Metadata (4)
    "sp_help",
    "sp_helptext",
    "sp_helpindex",
    "sp_helpconstraint",
    # Session/Server (3)
    "sp_who",
    "sp_who2",
    "sp_spaceused",
    # Result Set Metadata (2)
    "sp_describe_first_result_set",
    "sp_describe_undeclared_parameters",
})

logger = get_logger(__name__)

# Types that indicate a garbage parse (not real SQL statements)
_GARBAGE_PARSE_TYPES = (exp.Alias, exp.Column, exp.Identifier, exp.Literal)


def validate_query(sql: str, allow_write: bool = False) -> ValidationResult:
    """Validate a SQL query against the AST-based denylist.

    Pure function — no side effects, no database connection required.

    Args:
        sql: Raw SQL text
        allow_write: If True, DML operations (INSERT/UPDATE/DELETE/MERGE) are allowed

    Returns:
        ValidationResult with is_safe and categorized denial reasons
    """
    if not sql or not sql.strip():
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, "Empty or whitespace-only query", 0)],
        )

    try:
        statements = sqlglot.parse(sql, dialect="tsql")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, str(e), 0)],
        )

    if not statements or all(s is None for s in statements):
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, "No statements parsed", 0)],
        )

    reasons: list[DenialReason] = []
    for idx, stmt in enumerate(statements):
        if stmt is None:
            continue
        reasons.extend(_classify_statement(stmt, idx))

    # allow_write bypass: remove DML and CTE-wrapped write denials
    if allow_write:
        reasons = [r for r in reasons if r.category not in (DenialCategory.DML, DenialCategory.CTE_WRAPPED_WRITE)]

    return ValidationResult(is_safe=len(reasons) == 0, reasons=reasons)


def _classify_statement(stmt: exp.Expression, idx: int) -> list[DenialReason]:
    """Classify a single parsed statement and return denial reasons (if any)."""
    # Garbage parse detection (e.g., DBCC → Alias)
    if isinstance(stmt, _GARBAGE_PARSE_TYPES):
        return [DenialReason(DenialCategory.PARSE_FAILURE, "Unrecognized statement", idx)]

    # Execute/ExecuteSql (sqlglot >=29): EXEC/EXECUTE → stored procedure check
    if isinstance(stmt, exp.Execute):
        return _check_execute(stmt, idx)

    # Command: EXEC/EXECUTE (sqlglot <29) or other unrecognized commands → Operational
    # Must be checked before DENIED_TYPES since Command is in that map
    if isinstance(stmt, exp.Command):
        return _check_command(stmt, idx)

    # Kill → Operational (not in DENIED_TYPES to avoid confusion with Command handling)
    if isinstance(stmt, exp.Kill):
        return [DenialReason(DenialCategory.OPERATIONAL, "KILL operations are not permitted", idx)]

    # Check against denied types map
    for denied_type, category in DENIED_TYPES.items():
        if isinstance(stmt, denied_type):
            # CTE-wrapped write: DML with a WITH clause
            if category == DenialCategory.DML and stmt.find(exp.With):
                return [DenialReason(
                    DenialCategory.CTE_WRAPPED_WRITE,
                    f"CTE-wrapped {type(stmt).__name__.upper()} operations are not permitted",
                    idx,
                )]
            detail = f"{type(stmt).__name__.upper()} operations are not permitted"
            return [DenialReason(category, detail, idx)]

    # Select: check for INTO (creates a table)
    if isinstance(stmt, exp.Select) and stmt.find(exp.Into):
        return [DenialReason(DenialCategory.SELECT_INTO, "SELECT INTO creates a new table and is not permitted", idx)]

    # Control flow blocks (IF/WHILE): walk AST for nested denied operations
    if isinstance(stmt, _CONTROL_FLOW_TYPES):
        return _check_control_flow(stmt, idx)

    return []


def _check_execute(stmt: exp.Execute, idx: int) -> list[DenialReason]:
    """Check an Execute node (sqlglot >=29 EXEC/EXECUTE)."""
    # ExecuteSql is a subclass of Execute for sp_executesql
    if isinstance(stmt, exp.ExecuteSql):
        return [DenialReason(
            DenialCategory.STORED_PROCEDURE,
            "sp_executesql is explicitly denied (executes arbitrary SQL)",
            idx,
        )]

    # Extract procedure name from the Table node in stmt.this
    proc_table = stmt.this
    if proc_table and hasattr(proc_table, "this"):
        proc_name = str(proc_table.this)
    else:
        proc_name = str(proc_table) if proc_table else ""

    canonical = proc_name.rsplit(".", 1)[-1].lower()

    if canonical in SAFE_PROCEDURES:
        return []

    return [DenialReason(
        DenialCategory.STORED_PROCEDURE,
        f"Stored procedure '{proc_name}' is not in the safe allowlist",
        idx,
    )]


def _check_control_flow(stmt: exp.Expression, idx: int) -> list[DenialReason]:
    """Check a control flow block (IF/WHILE) for nested denied operations."""
    # Walk the AST looking for any denied operation nested inside
    for node in stmt.walk():
        if node is stmt:
            continue
        for denied_type, category in DENIED_TYPES.items():
            if isinstance(node, denied_type):
                block_type = type(stmt).__name__.replace("Block", "").upper()
                detail = f"{type(node).__name__.upper()} inside {block_type} block is not permitted"
                return [DenialReason(category, detail, idx)]
        # Also check for nested Execute
        if isinstance(node, exp.Execute):
            nested = _check_execute(node, idx)
            if nested:
                return nested

    # If the block was misparsed (no recognizable body), treat as unsafe
    # sqlglot may not fully parse T-SQL control flow, so deny conservatively
    block_type = type(stmt).__name__.replace("Block", "").upper()
    return [DenialReason(
        DenialCategory.OPERATIONAL,
        f"{block_type} control flow blocks are not permitted",
        idx,
    )]


def _check_command(stmt: exp.Command, idx: int) -> list[DenialReason]:
    """Check a Command node (EXEC/EXECUTE or other unrecognized command)."""
    cmd_name = str(stmt.this).upper() if stmt.this else ""
    if cmd_name in ("EXEC", "EXECUTE"):
        return _check_stored_procedure(stmt, idx)
    return [DenialReason(DenialCategory.OPERATIONAL, f"{cmd_name} operations are not permitted", idx)]


def _check_stored_procedure(stmt: exp.Command, idx: int) -> list[DenialReason]:
    """Check if a stored procedure call is in the safe allowlist."""
    # Extract procedure name from the expression arg
    proc_expr = stmt.args.get("expression")
    proc_name = str(proc_expr.this) if proc_expr else ""
    # For multi-part names (master.dbo.sp_help), take the last part
    canonical = proc_name.rsplit(".", 1)[-1].lower()

    if canonical == "sp_executesql":
        return [DenialReason(
            DenialCategory.STORED_PROCEDURE,
            "sp_executesql is explicitly denied (executes arbitrary SQL)",
            idx,
        )]

    if canonical in SAFE_PROCEDURES:
        return []

    return [DenialReason(
        DenialCategory.STORED_PROCEDURE,
        f"Stored procedure '{proc_name}' is not in the safe allowlist",
        idx,
    )]
