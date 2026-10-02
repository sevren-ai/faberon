#!/usr/bin/env bash
# Run the test suite CI runs, locally. Exits non-zero on failure.
# Mirrors .github/workflows/test.yml.
#
# Usage: bash scripts/test/local.sh

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
brain="$repo_root/packages/control-plane"
console="$repo_root/packages/console"

cd "$brain"

echo ">> uv sync --locked"
uv sync --locked

echo ">> pytest"
uv run pytest -rs

cd "$console"

echo ">> npm ci --legacy-peer-deps"
npm ci --legacy-peer-deps --no-audit --no-fund

echo ">> vitest run"
npx vitest run

echo "Tests passed."
