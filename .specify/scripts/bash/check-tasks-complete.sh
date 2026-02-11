#!/usr/bin/env bash
# Check if all tasks in a feature's tasks.md are complete
#
# Usage: ./check-tasks-complete.sh [OPTIONS] [FEATURE_DIR]
#
# OPTIONS:
#   --json       Output in JSON format
#   --quiet      Suppress output, just return exit code
#   --help, -h   Show help message
#
# FEATURE_DIR: Path to feature directory (e.g., specs/001-db-schema-explorer)
#              If not provided, uses current branch to find feature dir
#
# EXIT CODES:
#   0 - All tasks complete
#   1 - Incomplete tasks found
#   2 - Error (file not found, parse error, etc.)

set -e

# Parse command line arguments
JSON_MODE=false
QUIET_MODE=false
FEATURE_DIR=""

for arg in "$@"; do
    case "$arg" in
        --json)
            JSON_MODE=true
            ;;
        --quiet)
            QUIET_MODE=true
            ;;
        --help|-h)
            cat << 'EOF'
Usage: check-tasks-complete.sh [OPTIONS] [FEATURE_DIR]

Check if all tasks in a feature's tasks.md are complete.

OPTIONS:
  --json       Output in JSON format
  --quiet      Suppress output, just return exit code
  --help, -h   Show this help message

FEATURE_DIR: Path to feature directory (e.g., specs/001-db-schema-explorer)
             If not provided, uses current branch to find feature dir

EXIT CODES:
  0 - All tasks complete
  1 - Incomplete tasks found
  2 - Error (file not found, parse error, etc.)

EXAMPLES:
  # Check current feature branch
  ./check-tasks-complete.sh

  # Check specific feature
  ./check-tasks-complete.sh specs/001-db-schema-explorer

  # JSON output for tooling
  ./check-tasks-complete.sh --json specs/001-db-schema-explorer
EOF
            exit 0
            ;;
        -*)
            echo "ERROR: Unknown option '$arg'. Use --help for usage information." >&2
            exit 2
            ;;
        *)
            # Positional argument - feature directory
            FEATURE_DIR="$arg"
            ;;
    esac
done

# Source common functions if feature dir not provided
if [[ -z "$FEATURE_DIR" ]]; then
    SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    source "$SCRIPT_DIR/common.sh"
    eval $(get_feature_paths)
else
    # Normalize the path
    if [[ ! "$FEATURE_DIR" = /* ]]; then
        FEATURE_DIR="$(pwd)/$FEATURE_DIR"
    fi
fi

TASKS_FILE="$FEATURE_DIR/tasks.md"

# Validate tasks.md exists
if [[ ! -f "$TASKS_FILE" ]]; then
    if $JSON_MODE; then
        echo '{"error":"tasks.md not found","path":"'"$TASKS_FILE"'"}'
    elif ! $QUIET_MODE; then
        echo "ERROR: tasks.md not found at $TASKS_FILE" >&2
    fi
    exit 2
fi

# Count complete and incomplete tasks
# Tasks are lines starting with "- [x]" or "- [X]" (complete) or "- [ ]" (incomplete)
TOTAL_TASKS=$(grep -ciE '^\s*-\s*\[(x| )\]' "$TASKS_FILE" 2>/dev/null) || TOTAL_TASKS=0
COMPLETE_TASKS=$(grep -ciE '^\s*-\s*\[x\]' "$TASKS_FILE" 2>/dev/null) || COMPLETE_TASKS=0
INCOMPLETE_TASKS=$(grep -cE '^\s*-\s*\[ \]' "$TASKS_FILE" 2>/dev/null) || INCOMPLETE_TASKS=0

# Get list of incomplete task IDs for reporting
INCOMPLETE_LIST=""
if [[ "$INCOMPLETE_TASKS" -gt 0 ]]; then
    # Extract task description (remove leading whitespace and "- [ ] " prefix)
    INCOMPLETE_LIST=$(grep -E '^\s*-\s*\[ \]' "$TASKS_FILE" | sed 's/^[[:space:]]*- \[ \] //' | head -10)
fi

# Determine result
if [[ "$TOTAL_TASKS" -eq 0 ]]; then
    STATUS="error"
    MESSAGE="No tasks found in tasks.md"
    EXIT_CODE=2
elif [[ "$INCOMPLETE_TASKS" -eq 0 ]]; then
    STATUS="complete"
    MESSAGE="All $TOTAL_TASKS tasks complete"
    EXIT_CODE=0
else
    STATUS="incomplete"
    MESSAGE="$INCOMPLETE_TASKS of $TOTAL_TASKS tasks incomplete"
    EXIT_CODE=1
fi

# Output results
if $JSON_MODE; then
    # Build incomplete tasks JSON array
    if [[ -n "$INCOMPLETE_LIST" ]]; then
        # Convert newline-separated list to JSON array (no jq dependency)
        incomplete_json="[$(echo "$INCOMPLETE_LIST" | sed 's/\\/\\\\/g; s/"/\\"/g; s/.*/"&"/' | paste -sd, -)]"
    else
        incomplete_json="[]"
    fi

    cat <<EOF
{"status":"$STATUS","total":$TOTAL_TASKS,"complete":$COMPLETE_TASKS,"incomplete":$INCOMPLETE_TASKS,"message":"$MESSAGE","incomplete_tasks":$incomplete_json}
EOF
elif ! $QUIET_MODE; then
    echo "Task Completion Check: $MESSAGE"
    if [[ "$INCOMPLETE_TASKS" -gt 0 ]]; then
        echo ""
        echo "Incomplete tasks:"
        echo "$INCOMPLETE_LIST" | while read -r task; do
            echo "  [ ] $task"
        done
        if [[ "$INCOMPLETE_TASKS" -gt 10 ]]; then
            echo "  ... and $((INCOMPLETE_TASKS - 10)) more"
        fi
    fi
fi

exit $EXIT_CODE
