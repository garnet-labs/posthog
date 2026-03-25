#!/bin/bash
#
# Migrates permissions from settings.json to settings.local.json.
# The CLI's "Always allow" button writes to settings.json, but we want
# personal permissions in settings.local.json so they don't get committed.
#
# Triggered by ConfigChange hook, so must handle concurrent invocations
# and avoid corrupting settings.local.json.

SETTINGS="$CLAUDE_PROJECT_DIR/.claude/settings.json"
LOCAL="$CLAUDE_PROJECT_DIR/.claude/settings.local.json"
LOCKFILE="$CLAUDE_PROJECT_DIR/.claude/.migrate-permissions.lock"

# Use mkdir as an atomic lock (works on macOS and Linux)
if ! mkdir "$LOCKFILE" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCKFILE" 2>/dev/null' EXIT

python3 -c "
import json, sys, os, tempfile

settings_path = '$SETTINGS'
local_path = '$LOCAL'

# Read settings.json
try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)

# Check if there are permissions to migrate
allow = settings.get('permissions', {}).get('allow', [])
if not allow:
    sys.exit(0)

# Read settings.local.json — abort if it exists but can't be parsed
if os.path.exists(local_path):
    try:
        with open(local_path) as f:
            local = json.load(f)
    except (json.JSONDecodeError, OSError):
        # File exists but is corrupt or being written — don't risk losing data
        sys.exit(1)
else:
    local = {}

# Merge allow lists, deduplicate while preserving order
local_perms = local.setdefault('permissions', {})
existing = local_perms.get('allow', [])
seen = set(existing)
for entry in allow:
    if entry not in seen:
        existing.append(entry)
        seen.add(entry)
local_perms['allow'] = existing

# Write settings.local.json atomically via temp file
dir_path = os.path.dirname(local_path)
fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.json')
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(local, f, indent=2)
        f.write('\n')
    os.replace(tmp_path, local_path)
except:
    os.unlink(tmp_path)
    sys.exit(1)

# Remove permissions from settings.json atomically
del settings['permissions']
fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.json')
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    os.replace(tmp_path, settings_path)
except:
    os.unlink(tmp_path)
    sys.exit(1)
"

exit 0
