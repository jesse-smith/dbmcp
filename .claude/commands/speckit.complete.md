---
description: Mark a feature as complete after merging to main. Updates status headers and central registry.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

This skill ensures consistent feature completion tracking across the project. Run this after merging a feature branch to main.

## Steps

1. **Identify the feature**: Determine which feature was just completed.
   - If no argument provided, check recent git history for merged feature branches
   - Feature branches follow the pattern `###-feature-name` (e.g., `001-db-schema-explorer`)

2. **Locate feature documents**: Find all spec files in `specs/[###-feature-name]/`
   - Required: spec.md, plan.md, tasks.md
   - Optional: research.md, data-model.md, quickstart.md

3. **Add status headers**: Add a completion header to each document immediately after the first heading:

   For spec.md:
   ```markdown
   # Feature Specification: [Name]

   > **STATUS: COMPLETE** | Merged: [YYYY-MM-DD] | Branch: `###-feature-name`
   ```

   For plan.md:
   ```markdown
   # Implementation Plan: [Name]

   > **STATUS: COMPLETE** | Merged: [YYYY-MM-DD] | Branch: `###-feature-name`
   ```

   For tasks.md:
   ```markdown
   # Tasks: [Name]

   > **STATUS: COMPLETE** | Merged: [YYYY-MM-DD] | Branch: `###-feature-name`
   ```

4. **Update central registry**: Edit `specs/STATUS.md`:
   - Find the row for this feature
   - Change Status to "Complete"
   - Add the Merged Date
   - Update Notes if needed

5. **Commit the changes**:
   ```
   git add specs/
   git commit -m "docs: Mark [feature-name] as complete"
   ```

## Notes

- If a feature is being archived (not fully implemented), use Status: "Archived" and explain in Notes
- The hookify plugin will remind you to run this skill after feature branch merges
- This skill does NOT push to remote - that's a separate action
