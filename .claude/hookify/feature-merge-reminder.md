---
name: feature-merge-reminder
enabled: true
event: bash
pattern: git\s+merge\s+\d{3}-
action: warn
---

**Feature branch merge detected!**

Run `/speckit.complete` to:
- Add status headers to spec.md, plan.md, tasks.md
- Update specs/STATUS.md registry

This ensures the feature is properly marked as complete.
