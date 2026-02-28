#!/usr/bin/env python3
"""Run complexipy and filter out disabled-tool functions.

Exits 0 if all active-code functions pass, 1 otherwise.
"""

import json
import subprocess
import sys
from pathlib import Path

MAX_COMPLEXITY = 15

# Directories that only support disabled MCP tools.
# Passed to complexipy's --exclude flag (matches directory names only).
EXCLUDED_DIRS = [
    "cache",
    "inference",
]

# Individual disabled-tool functions to exclude from failure checks.
# Format: (file_name_suffix, function_name)
# Note: complexipy --exclude only works for directories, not files,
# so file-level exclusions must be handled via post-filtering here.
EXCLUDED_FUNCTIONS = [
    ("doc_tools.py", "export_documentation"),
    ("doc_tools.py", "load_cached_docs"),
    ("doc_tools.py", "check_drift"),
    ("schema_tools.py", "infer_relationships"),
    ("query_tools.py", "analyze_column"),
]


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent

    exclude_args = []
    for path in EXCLUDED_DIRS:
        exclude_args.extend(["-e", path])

    subprocess.run(
        ["complexipy", "src/", *exclude_args, "-j", "-q", "--color", "no"],
        cwd=project_root,
        capture_output=True,
    )

    # complexipy writes to cwd with a timestamped name
    json_files = sorted(project_root.glob("complexipy_results_*.json"))
    if not json_files:
        print("ERROR: complexipy did not produce output")
        return 1

    results_file = json_files[-1]
    results = json.loads(results_file.read_text())
    results_file.unlink()

    failures = []
    for entry in results:
        if entry["complexity"] <= MAX_COMPLEXITY:
            continue

        path = entry["path"]
        func = entry["function_name"]

        # Strip class prefix for matching (e.g. "Class::method" -> "method")
        bare_func = func.split("::")[-1] if "::" in func else func

        excluded = any(
            path.endswith(suffix) and bare_func == excl_func
            for suffix, excl_func in EXCLUDED_FUNCTIONS
        )
        if excluded:
            continue

        failures.append(entry)

    if failures:
        print(f"Complexity check FAILED — {len(failures)} function(s) exceed max of {MAX_COMPLEXITY}:")
        for f in sorted(failures, key=lambda x: -x["complexity"]):
            print(f"  {f['path']}::{f['function_name']} = {f['complexity']}")
        return 1

    print(f"Complexity check passed (max={MAX_COMPLEXITY})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
