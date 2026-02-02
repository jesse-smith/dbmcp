# Feature Status Registry

Central registry of all features and their current status.

| Feature ID | Name | Branch | Status | Merged Date | Notes |
|------------|------|--------|--------|-------------|-------|
| 001 | DB Schema Explorer | `001-db-schema-explorer` | Complete | 2026-02-02 | All 11 phases implemented |
| 002 | Example Notebooks | `002-example-notebooks` | Archived | 2026-01-20 | Workflow changed: notebooks now tracked in 001 |
| 003 | Speckit Workflow Integration | `003-speckit-workflow-integration` | Complete | 2026-01-26 | Tooling feature - no spec docs |

## Status Definitions

- **Draft**: Initial specification, not yet approved
- **In Progress**: Active development on feature branch
- **Complete**: All tasks finished, merged to main
- **Archived**: Feature closed without full implementation (see Notes)

## Usage

When completing a feature branch merge:

1. Run `/speckit.complete` to update this registry
2. Add status headers to spec.md, plan.md, tasks.md
3. Commit the status updates
