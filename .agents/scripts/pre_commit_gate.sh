#!/usr/bin/env bash
# PreToolUse Quality & Safety Gate for Antigravity (PreToolUse on run_command)
# Intercepts 'git commit' commands to verify linting and type-checking before committing.
set -e

# Read stdin JSON payload from Antigravity
PAYLOAD=$(cat)

# Extract CommandLine from payload
CMD=$(python3 -c '
import sys, json
try:
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)
    cmd = payload.get("toolCall", {}).get("args", {}).get("CommandLine", "")
    print(cmd)
except Exception:
    print("")
' "$PAYLOAD" 2>/dev/null || echo "")

# If not a git commit command, immediately allow
case "$CMD" in
  *"git commit"*)
    ;;
  *)
    echo '{"decision": "allow"}'
    exit 0
    ;;
esac

FAILURES=""

# Fail-open check: only run ruff if installed and src/ or tests/ directory exists
if command -v ruff >/dev/null 2>&1; then
  TARGETS=""
  [ -d "src" ] && TARGETS="$TARGETS src/"
  [ -d "tests" ] && TARGETS="$TARGETS tests/"
  if [ -n "$TARGETS" ]; then
    if ! ruff check $TARGETS >/dev/null 2>&1; then
      FAILURES="${FAILURES} [ruff lint check failed]"
    fi
  fi
fi

# Fail-open check: only run mypy if installed and src/ directory exists
if command -v mypy >/dev/null 2>&1; then
  if [ -d "src" ]; then
    if ! mypy src/ >/dev/null 2>&1; then
      FAILURES="${FAILURES} [mypy type check failed]"
    fi
  fi
fi

# If failures were detected, deny the tool execution
if [ -n "$FAILURES" ]; then
  python3 -c '
import sys, json
reason = "Pre-commit gate denied execution:" + sys.argv[1]
print(json.dumps({"decision": "deny", "reason": reason}))
' "$FAILURES"
else
  echo '{"decision": "allow"}'
fi

exit 0
