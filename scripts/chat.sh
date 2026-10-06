#!/usr/bin/env bash
# Start a Pi chat session with the Faberon Chat extension loaded from
# source. Works from any cwd. Any extra arguments are passed through to Pi.
#
#   scripts/chat.sh
#   scripts/chat.sh --help

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
chat="$repo_root/packages/chat"
pi_bin="$chat/node_modules/.bin/pi"

fail() {
  echo "chat: $*" >&2
  exit 1
}

command -v node >/dev/null 2>&1 || fail "node is not on PATH. Install Node.js >= 22.19."
command -v npm >/dev/null 2>&1 || fail "npm is not on PATH. Install Node.js >= 22.19."

node_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
if [ "$node_major" -lt 22 ]; then
  fail "node $(node --version) is too old; Faberon Chat requires Node.js >= 22.19."
fi

if [ ! -x "$pi_bin" ]; then
  echo ">> chat dependencies missing; running npm ci"
  (cd "$chat" && npm ci --legacy-peer-deps --no-audit --no-fund)
fi

[ -x "$pi_bin" ] || fail "npm ci did not produce $pi_bin. See the output above."

exec "$pi_bin" -e "$chat/src/index.ts" "$@"
