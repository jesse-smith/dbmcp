# Deferred Items

- [15-06] Pre-existing E402 (module-level import not at top) in tests/unit/test_async_tools.py:281-282 — mid-file import block added by Plans 04/05. Present at base 08d712f; out of scope for 15-06. Fix: move imports to top or add `# noqa: E402` / ruff per-file-ignore.
