#!/bin/bash
# PreToolUse hook: ensures `gh pr create` commands follow the PR template.
# Reads tool input JSON from stdin. Exits non-zero to block non-compliant calls.
# Sections are inferred from .github/pull_request_template.md (including commented-out ones).

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

# Only check gh pr create commands
if ! echo "$COMMAND" | grep -q "gh pr create"; then
    exit 0
fi

TEMPLATE="$CLAUDE_PROJECT_DIR/.github/pull_request_template.md"
if [ ! -f "$TEMPLATE" ]; then
    exit 0
fi

# Extract all ## headings from the template, including commented-out ones (<!-- ## ... -->)
# Strip HTML comment markers so we get the raw heading text
REQUIRED_SECTIONS=()
while IFS= read -r line; do
    # Match lines like "## Foo" or "<!-- ## Foo -->" (with optional leading whitespace)
    cleaned=$(echo "$line" | sed -E 's/^[[:space:]]*<!-- *//; s/ *-->.*$//; s/^[[:space:]]*//')
    if echo "$cleaned" | grep -qE '^## '; then
        REQUIRED_SECTIONS+=("$cleaned")
    fi
done < "$TEMPLATE"

if [ ${#REQUIRED_SECTIONS[@]} -eq 0 ]; then
    exit 0
fi

MISSING=()
for section in "${REQUIRED_SECTIONS[@]}"; do
    if ! echo "$COMMAND" | grep -qF "$section"; then
        MISSING+=("$section")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "BLOCKED: PR body is missing required template sections from .github/pull_request_template.md:"
    for section in "${MISSING[@]}"; do
        echo "  - $section"
    done
    echo ""
    echo "Commented-out sections (like <!-- ## 🤖 LLM context -->) should be uncommented since this PR is authored/co-authored by an LLM agent."
    exit 2
fi

exit 0
