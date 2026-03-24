#!/bin/bash
# PreToolUse hook: ensures `gh pr create` commands follow the PR template.
# Reads tool input JSON from stdin. Exits non-zero to block non-compliant calls.
# Sections are inferred from .github/pull_request_template.md (including commented-out ones).

set -euo pipefail

INPUT=$(cat)

# Fast path: skip Python entirely if "gh pr create" doesn't appear anywhere in the input
if ! echo "$INPUT" | grep -qF "gh pr create"; then
    exit 0
fi

# Use Python for all parsing to handle heredocs, --body-file, and edge cases correctly
echo "$INPUT" | python3 -c "
import sys, json, re, os

raw = sys.stdin.read()
try:
    command = json.loads(raw).get('tool_input', {}).get('command', '')
except (json.JSONDecodeError, AttributeError):
    sys.exit(0)

# Strip heredoc bodies and quoted strings to check if 'gh pr create' is
# the actual command being run (not just mentioned in a commit message, etc.)
stripped = re.sub(r\"<<'?\\\"?EOF\\\"?'?.*?^EOF$\", '', command, flags=re.DOTALL | re.MULTILINE)
stripped = re.sub(r'\"[^\"]*\"', '', stripped)
stripped = re.sub(r\"'[^']*'\", '', stripped)

if 'gh pr create' not in stripped:
    sys.exit(0)

# Load the PR template
template_path = os.path.join(os.environ.get('CLAUDE_PROJECT_DIR', '.'), '.github', 'pull_request_template.md')
if not os.path.isfile(template_path):
    sys.exit(0)

with open(template_path) as f:
    template = f.read()

# Extract all ## headings (including commented-out ones like <!-- ## ... -->)
required = []
for line in template.splitlines():
    cleaned = re.sub(r'^\\s*<!--\\s*', '', line)
    cleaned = re.sub(r'\\s*-->.*$', '', cleaned).strip()
    if cleaned.startswith('## '):
        required.append(cleaned)

if not required:
    sys.exit(0)

# Resolve body content: handle --body-file or use the full command (which includes inline --body / heredoc)
body = command
body_file_match = re.search(r'--body-file[= ]*[\\'\"]?([^\\'\"\\ ]+)', command)
if body_file_match:
    path = body_file_match.group(1)
    if os.path.isfile(path):
        with open(path) as f:
            body = f.read()
    else:
        print('BLOCKED: --body-file target not readable. Use inline --body with a heredoc instead.')
        sys.exit(2)

# Check for missing sections
missing = [s for s in required if s not in body]
if missing:
    print('BLOCKED: PR body is missing required template sections from .github/pull_request_template.md:')
    for s in missing:
        print(f'  - {s}')
    print()
    print('All sections from the template must be present, including any commented-out ones')
    print('(uncomment them since this PR is authored/co-authored by an LLM agent).')
    sys.exit(2)
"
