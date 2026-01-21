# Notebook Structure Contract

**Feature**: 002-example-notebooks
**Date**: 2026-01-20
**Purpose**: Define standardized structure for all DBMCP example notebooks

## Overview

All example notebooks MUST follow this structure to ensure consistency, maintainability, and user experience quality.

## Required Structure

### Cell 1: Title and Metadata (Markdown)

```markdown
# [Notebook Title]

**Notebook Version**: [semver]
**Compatible with DBMCP**: [version range]
**Last Updated**: [YYYY-MM-DD]
**Test Database Version**: [version]
**Estimated Time**: [N] minutes
**Difficulty**: [Beginner|Intermediate|Advanced]
```

**Requirements**:
- Title uses H1 heading
- All metadata fields present
- Version follows semantic versioning
- Date in ISO 8601 format

---

### Cell 2: Overview and Prerequisites (Markdown)

```markdown
## Overview

[2-3 sentences describing what this notebook demonstrates]

## Prerequisites

- [Required knowledge/setup item 1]
- [Required knowledge/setup item 2]

## What You'll Learn

- [Learning objective 1]
- [Learning objective 2]
- [Learning objective 3]
```

**Requirements**:
- Clear value proposition in overview
- Explicit prerequisites listed
- 3-5 concrete learning objectives

---

### Cell 3: Environment Verification (Code)

```python
# Verify notebook environment and display versions
import sys
print(f"Python version: {sys.version}")

try:
    import mcp
    print(f"MCP version: {mcp.__version__}")
except ImportError:
    print("⚠️ MCP not installed. Run: pip install mcp[cli]")

try:
    from examples.shared.notebook_helpers import verify_notebook_environment
    if not verify_notebook_environment():
        print("⚠️ Some dependencies missing. Check output above.")
except ImportError:
    print("ℹ️ Run this notebook from repository root for full functionality.")
```

**Requirements**:
- Check critical dependencies
- Display versions for debugging
- Provide actionable error messages if missing

---

### Cell 4-N: Content Sections

Each content section MUST follow this pattern:

#### Markdown Cell: Section Introduction
```markdown
## [Section N]: [Section Title]

[1-2 paragraphs explaining what this section demonstrates and why it matters]

**What we'll do**:
1. [Step 1 description]
2. [Step 2 description]
3. [Step 3 description]
```

#### Code Cell: Implementation
```python
# [Descriptive comment explaining the operation]

# Actual implementation code
result = some_operation()

# Display results with context
print(f"Result: {result}")
```

#### Markdown Cell: Explanation
```markdown
**Understanding the results**:

[Explanation of what just happened, what the output means, and any important patterns or gotchas]

**Key takeaways**:
- [Insight 1]
- [Insight 2]
```

**Requirements**:
- Every code cell has accompanying markdown explanation before/after
- Code includes inline comments for complex operations
- Results are displayed with context (not just raw values)
- Takeaways summarize learning points

---

### Cell N-2: Error Handling Demonstration (if applicable)

For notebooks demonstrating error scenarios:

```python
# Demonstrate [error scenario] handling

try:
    # Code that produces expected error
    result = operation_that_fails()
except SpecificError as e:
    print(f"✓ Expected error caught: {e}")
    print("\n**Recovery approach**:")
    print("In production code, you would:")
    print("1. [Recovery step 1]")
    print("2. [Recovery step 2]")
```

**Requirements**:
- Error handling shown via try/except (not failing cells)
- Clearly labeled as "expected" error
- Provides guidance on production recovery strategies

---

### Cell N-1: Summary (Markdown)

```markdown
## Summary

**What we covered**:
- ✓ [Accomplishment 1]
- ✓ [Accomplishment 2]
- ✓ [Accomplishment 3]

**Key concepts**:
- **[Concept 1]**: [Brief explanation]
- **[Concept 2]**: [Brief explanation]

**Common pitfalls**:
⚠️ [Pitfall 1]: [How to avoid]
⚠️ [Pitfall 2]: [How to avoid]
```

**Requirements**:
- Recap of what was demonstrated (checklist format)
- Highlight 2-3 key concepts with brief explanations
- List common mistakes and how to avoid them

---

### Cell N: Next Steps (Markdown)

```markdown
## Next Steps

**Continue learning**:
- 📓 [Next notebook in sequence] - [What it covers]
- 📓 [Related notebook] - [What it covers]

**Explore further**:
- 📖 [Link to relevant documentation]
- 💡 Try modifying this notebook to [suggested exploration activity]

**Need help?**
- 🐛 [Link to issue tracker]
- 💬 [Link to discussions/community]
```

**Requirements**:
- Links to next logical notebook(s)
- Suggestions for self-directed exploration
- Pointers to documentation and community resources
- All links must be valid (tested in CI)

---

## Formatting Standards

### Code Style
- Follow PEP 8 for Python code
- Maximum line length: 88 characters (Black default)
- Use descriptive variable names (no single letters except loop indices)
- Include type hints for function definitions in helper imports

### Markdown Style
- Use sentence case for headings
- Maximum 80 characters per line for paragraph text
- Use emoji sparingly and consistently:
  - ✓ for completed/successful items
  - ⚠️ for warnings/pitfalls
  - ℹ️ for informational notes
  - 📓 for notebook links
  - 📖 for documentation links
  - 🐛 for bugs/issues
  - 💬 for community/discussions
  - 💡 for ideas/suggestions

### Output Display
- Results should be formatted for readability
- Use tables for tabular data
- Truncate long outputs with "..." and row counts
- Include units in numerical results (e.g., "42 ms" not "42")

---

## Validation Contract

Every notebook MUST:
1. Execute successfully from top to bottom ("Run All")
2. Complete in under stated estimated time
3. Produce expected outputs (verified via nbval in CI)
4. Pass ruff linting on all code cells
5. Contain no hardcoded credentials or file paths (except relative to repo root)
6. Work with test database schema at specified version
7. Be committed WITH outputs (pre-executed)

---

## Maintenance Contract

When updating notebooks:
1. Increment version number (patch for typos, minor for content updates, major for restructuring)
2. Update "Last Updated" date
3. Re-execute all cells to update outputs
4. Verify all links still valid
5. Check compatibility version range still accurate
6. Update example index in README if title/objectives change
7. Run pytest suite to verify notebook still passes

---

## Anti-Patterns (Forbidden)

❌ **DO NOT**:
- Leave notebooks with cleared outputs
- Include cells that always fail (use try/except for error demos)
- Use hardcoded connection strings with credentials
- Create notebooks longer than 30 cells (split instead)
- Reference external files outside repository structure
- Use deprecated DBMCP APIs without clear warnings
- Include TODO or placeholder cells in committed notebooks
- Mix concerns (one notebook = one coherent topic)

---

## Examples

See implemented notebooks for reference:
- `examples/notebooks/01_basic_connection.ipynb` - Basic structure
- `examples/notebooks/02_table_inspection.ipynb` - Intermediate depth
- `examples/notebooks/03_advanced_patterns.ipynb` - Advanced with error handling
