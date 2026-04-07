#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

ENUM_NAMES_FILE="$SCRIPT_DIR/enum-names.json"
EXTENSIONS="--extensions=ts,tsx"
IGNORE="--ignore-pattern=**/node_modules/** --ignore-pattern=**/dist/** --ignore-pattern=**/generated/**"

# Directories to process (pass directories, not globs — jscodeshift uses --extensions to filter)
DIRS=(nodejs/src)

echo "=== Step 1: Collect all enum names ==="
# Collect enum names from the target directories
grep -rEoh '(export\s+)?(const\s+)?enum\s+(\w+)' \
  --include='*.ts' --include='*.tsx' \
  "${DIRS[@]}" 2>/dev/null \
  | sed -E 's/.* enum //' \
  | sort -u \
  | jq -R . | jq -s . > "$ENUM_NAMES_FILE"

COUNT=$(jq length "$ENUM_NAMES_FILE")
echo "Found $COUNT enum names, saved to $ENUM_NAMES_FILE"

echo ""
echo "=== Step 2: Convert enums to const objects ==="
npx jscodeshift --parser tsx \
  -t "$SCRIPT_DIR/enum-to-const-object.js" \
  --enumNames="$ENUM_NAMES_FILE" \
  $EXTENSIONS $IGNORE \
  "${DIRS[@]}"

echo ""
echo "=== Step 3: Convert parameter properties ==="
npx jscodeshift --parser tsx \
  -t "$SCRIPT_DIR/parameter-properties.js" \
  $EXTENSIONS $IGNORE \
  "${DIRS[@]}"

echo ""
echo "=== Done! Run 'cd nodejs && npx tsc --noEmit' to verify ==="
