# Research: Example Notebooks

**Feature**: 002-example-notebooks
**Date**: 2026-01-20
**Purpose**: Resolve technical unknowns and establish best practices for Jupyter notebook examples

## Research Areas

### 1. Jupyter Notebook Best Practices for Documentation

**Question**: What are the established patterns for creating educational Jupyter notebooks?

**Decision**: Follow Jupyter community standards for educational notebooks:
- Start with overview/prerequisites cell
- Alternate markdown explanations with code cells
- Include expected output in saved notebook (pre-executed)
- Use clear section headers with numbered progression
- End with "Next Steps" pointing to other resources

**Rationale**:
- Established pattern recognized by Python community
- Reduces cognitive load for users familiar with Jupyter ecosystem
- Pre-executed outputs allow users to verify their results match expected behavior
- Numbered notebooks (01_, 02_, 03_) provide clear progression

**Alternatives Considered**:
- Plain Python scripts with comments: Less interactive, harder to see output
- Markdown with code blocks: Not executable, defeats purpose of hands-on examples
- Interactive web documentation: Requires hosting infrastructure, adds complexity

**References**:
- Jupyter notebook documentation patterns
- Examples from major Python projects (pandas, scikit-learn)
- NumFOCUS recommended practices

---

### 2. Test Database Schema Design

**Question**: What should the test database contain to demonstrate all DBMCP features effectively?

**Decision**: Create minimal but representative schema with:
- 5-7 tables covering common patterns (users, orders, products, etc.)
- Declared foreign keys (for testing schema inspection)
- Undeclared relationships with naming patterns (for testing inference)
- Mix of data types (int, varchar, datetime, decimal)
- Varying table sizes (small reference tables, larger transactional tables)
- At least one many-to-many relationship via junction table

**Rationale**:
- Mirrors real-world e-commerce/CRM patterns users likely encounter
- Small enough to setup quickly (<5 seconds), large enough to be meaningful
- Includes both declared and undeclared FKs to demonstrate all features
- Familiar domain (e-commerce) requires no domain-specific knowledge

**Alternatives Considered**:
- Empty database: Doesn't demonstrate real capabilities
- Production-scale schema: Too complex, slow to setup, obscures learning
- Random synthetic tables: Lacks meaning, harder for users to understand relationships

**Implementation**: Use SQL Server LocalDB or SQLite for portability

---

### 3. Notebook Maintenance Strategy

**Question**: How do we keep notebooks synchronized with codebase changes?

**Decision**: Implement three-tier maintenance approach:
1. **Version indicators**: Add cell at top with last-updated date and compatible DBMCP version
2. **CI validation**: Add pytest test that executes notebooks with nbconvert/nbval
3. **Manual review**: Include notebook update in feature PR checklist when API changes

**Rationale**:
- Version indicators provide immediate visibility of notebook currency
- CI catches breaking changes before they reach users
- Manual review ensures examples reflect intentional API design
- Combination catches both technical failures and semantic drift

**Alternatives Considered**:
- Fully manual: Error-prone, notebooks fall out of date quickly
- Fully automated regeneration: Loses curated explanations and insights
- No version tracking: Users can't tell if notebooks work with their version

**Implementation**:
- Use nbval pytest plugin for notebook execution testing
- Add notebook tests to existing pytest suite
- Create .specify/templates/pr-checklist.md including notebook review

---

### 4. Connection Configuration Pattern

**Question**: How should notebooks handle database connection details securely?

**Decision**: Use environment variable pattern with fallback to local test database:
```python
import os
connection_string = os.getenv(
    "DBMCP_CONNECTION_STRING",
    "sqlite:///examples/test_database/example.db"  # Safe local fallback
)
```

**Rationale**:
- Prevents accidental credential commits
- Works out-of-box with provided test database (zero configuration)
- Allows users to override for their own databases (production use case)
- Standard pattern familiar to Python developers

**Alternatives Considered**:
- Hardcoded connections: Security risk, requires user modification
- Config file: Adds file management complexity, easier to commit accidentally
- Interactive prompts: Breaks cell-by-cell execution flow

---

### 5. Notebook Distribution Format

**Question**: Should notebooks be pre-executed or cleared before distribution?

**Decision**: Distribute WITH outputs (pre-executed) in repository

**Rationale**:
- Users can preview results without running (validates tool worth trying)
- Serves as regression test (visual diff shows if outputs change)
- Users can compare their output to expected output for debugging
- GitHub/GitLab render executed notebooks beautifully in web UI

**Alternatives Considered**:
- Cleared notebooks: Requires execution to see any value, unclear what to expect
- Separate outputs directory: Duplicates content, maintenance burden

**Implementation**:
- Execute notebooks with fresh test database before committing
- CI verifies outputs match (via nbval)
- Add note in README about re-running to verify local setup

---

### 6. Error Handling Demonstration

**Question**: How should notebooks demonstrate error scenarios without breaking execution flow?

**Decision**: Use try/except blocks with explanatory comments:
```python
# Demonstrate connection failure handling
try:
    connection = connect("invalid://connection")
except ConnectionError as e:
    print(f"Expected error: {e}")
    print("In production, you would: [recovery steps]")
```

**Rationale**:
- Shows both error and recovery in single cell
- Doesn't interrupt notebook flow (cell succeeds)
- Makes error handling explicit learning objective
- Provides template users can adapt

**Alternatives Considered**:
- Separate error notebook: Fragments learning, users skip error handling
- Comments only: Doesn't prove error handling works
- Failing cells: Breaks "Run All" workflow, looks like notebook is broken

---

## Summary

All technical decisions resolved. No NEEDS CLARIFICATION items remain. Ready for Phase 1 (Design).

**Key Takeaways**:
- Standard Jupyter patterns with pre-executed outputs
- Minimal e-commerce test database (5-7 tables)
- CI-validated notebooks with version indicators
- Environment variable configuration with safe local fallback
- Error handling demonstrated via try/except examples within flow
