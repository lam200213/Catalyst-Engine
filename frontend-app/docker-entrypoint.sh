#!/bin/sh
set -e

HASH_FILE=node_modules/.deps.hash
CURR_HASH="$(sha256sum package.json 2>/dev/null; sha256sum package-lock.json 2>/dev/null)"

# Check if node_modules exists and is populated.
# If not, run npm install.
if [ ! -d node_modules ] || [ ! -f "$HASH_FILE" ] || ! printf "%s" "$CURR_HASH" | diff -q - "$HASH_FILE" >/dev/null 2>&1; then
  echo "Installing deps (detected missing or changed manifest)..."
  npm ci || npm install
  mkdir -p node_modules
  printf "%s" "$CURR_HASH" > "$HASH_FILE"
fi

# Execute the main command (vite).
exec "$@"