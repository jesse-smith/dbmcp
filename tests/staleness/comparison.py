"""Bidirectional field set comparison with conditional field awareness.

Compares declared docstring fields (from extract_fields()) against actual
response keys, accounting for conditional annotations like '// on error only'.
"""


def _should_expect_field(
    field_name: str,
    conditional: dict[str, str],
    response_path: str,
) -> bool:
    """Determine if a field should be expected given the response path.

    Conditional rules:
    - "on error only" -> expected only when response_path == "error"
    - "on success only" -> expected only when response_path == "success"
    - "on error/blocked only" -> expected only when response_path in ("error", "blocked")
    - Any other annotation (e.g., "detailed mode only") -> treated as optional (never required)
    - No annotation -> always expected
    """
    if field_name not in conditional:
        return True  # No annotation = always expected

    condition = conditional[field_name].lower()

    if "on error" in condition and "only" in condition:
        return response_path == "error" or response_path == "blocked"
    if "on success" in condition and "only" in condition:
        return response_path == "success"

    # Any other condition (e.g., "detailed mode only", "numeric columns only")
    # is treated as optional -- we can't know if the condition was met
    return False


def compare_fields(
    declared: dict,
    actual_keys: set[str],
    actual_nested: dict[str, set[str]],
    response_path: str,
    tool_name: str,
) -> list[str]:
    """Compare declared docstring fields against actual response keys.

    Returns list of drift messages (empty = no drift).
    Conditional fields are excluded from comparison when their condition
    doesn't match the response_path (e.g., "on error only" fields skipped
    for success responses).
    """
    messages: list[str] = []

    top_level = declared["top_level"]
    nested = declared.get("nested", {})
    conditional = declared.get("conditional", {})

    # --- Top-level comparison ---

    # Fields we expect to be present given the response path
    expected = {
        f for f in top_level if _should_expect_field(f, conditional, response_path)
    }

    # All declared fields (including conditional) -- used to detect "extra" fields
    all_declared = top_level

    missing = expected - actual_keys
    extra = actual_keys - all_declared

    if missing:
        messages.append(
            f"Drift in {tool_name}: missing from response: {sorted(missing)}"
        )
    if extra:
        messages.append(
            f"Drift in {tool_name}: undocumented in response: {sorted(extra)}"
        )

    # --- Nested comparison ---

    for parent, declared_children in nested.items():
        if parent not in actual_nested:
            # Parent not in actual nested -- might be empty list or not present
            continue

        actual_children = actual_nested[parent]

        # Filter declared children by conditional annotations
        expected_children = {
            f
            for f in declared_children
            if _should_expect_field(f, conditional, response_path)
        }

        all_declared_children = declared_children

        nested_missing = expected_children - actual_children
        nested_extra = actual_children - all_declared_children

        if nested_missing:
            messages.append(
                f"Drift in {tool_name}.{parent}: missing from response: {sorted(nested_missing)}"
            )
        if nested_extra:
            messages.append(
                f"Drift in {tool_name}.{parent}: undocumented in response: {sorted(nested_extra)}"
            )

    return messages
