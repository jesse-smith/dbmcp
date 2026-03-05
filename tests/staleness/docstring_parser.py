"""Extract field declarations from TOON docstring Returns sections.

Parses the structured outline format used in MCP tool docstrings:

    Returns:
        TOON-encoded string with ...:

            status: "success" | "error"
            field_name: type              // annotation
            nested_list: list
                child_field: type
"""

import inspect
import re

# Matches field lines: leading whitespace, field_name, colon, type, optional // annotation
_FIELD_RE = re.compile(r"^(\s+)(\w+):\s+(.+?)(?:\s+//\s*(.+))?$")


def extract_fields(docstring: str | None) -> dict:
    """Extract field declarations from a TOON docstring Returns section.

    Returns dict with:
      "top_level": set of field names at top level
      "nested": dict mapping parent field -> set of child field names
      "conditional": dict mapping field name -> condition string (e.g., "on error only")
    """
    empty = {"top_level": set(), "nested": {}, "conditional": {}}
    if not docstring:
        return empty

    lines = inspect.cleandoc(docstring).splitlines()

    # Find the Returns: section
    returns_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "Returns:":
            returns_idx = i
            break

    if returns_idx is None:
        return empty

    top_level: set[str] = set()
    nested: dict[str, set[str]] = {}
    conditional: dict[str, str] = {}

    base_indent: int | None = None
    # Track which fields are list/object parents (can have children)
    current_parent: str | None = None
    current_parent_indent: int | None = None

    for line in lines[returns_idx + 1 :]:
        stripped = line.strip()

        # Stop at next section header: an unindented or low-indented line ending with ':'
        # that is NOT a field line (field lines have type info after the colon)
        if stripped and stripped.endswith(":") and base_indent is not None:
            line_indent = len(line) - len(line.lstrip())
            # Section headers are at or below base indent level
            if line_indent < base_indent:
                # Check it's not a field line (field lines have spaces after colon)
                if not _FIELD_RE.match(line):
                    break

        match = _FIELD_RE.match(line)
        if not match:
            continue

        indent = len(match.group(1))
        field_name = match.group(2)
        field_type = match.group(3).strip()
        annotation = match.group(4)

        if base_indent is None:
            base_indent = indent

        if annotation:
            conditional[field_name] = annotation

        if indent == base_indent:
            # Top-level field
            top_level.add(field_name)
            # Check if this field can be a parent (list or object type)
            if field_type in ("list", "object") or field_type.startswith("list"):
                current_parent = field_name
                current_parent_indent = indent
            else:
                current_parent = None
                current_parent_indent = None
        elif current_parent is not None and indent > current_parent_indent:
            # Nested child field (one level deep)
            if current_parent not in nested:
                nested[current_parent] = set()
            nested[current_parent].add(field_name)

            # Track sub-parents for depth > 1 (we still capture them as children
            # of the original parent, per the plan's "one level deep" rule)
            if field_type in ("list", "object") or field_type.startswith("list"):
                # This is a nested parent -- its own children are depth 2+
                # We capture it as a child of current_parent but don't recurse deeper
                pass

    return {"top_level": top_level, "nested": nested, "conditional": conditional}
