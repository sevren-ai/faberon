#!/usr/bin/env bash
# Run the lint checks CI runs, locally, and apply fixes. Exits non-zero on
# the first failure. Unlike .github/workflows/lint.yml, which checks only,
# this script writes fixes back to the source.

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
brain="$repo_root/packages/control-plane"
console="$repo_root/packages/console"

cd "$brain"

echo ">> uv sync --locked"
uv sync --locked

echo ">> ruff format src tests"
uv run ruff format src tests

echo ">> ruff check --fix src tests"
uv run ruff check --fix src tests

echo ">> ty check src tests"
uv run ty check src tests

cd "$console"

echo ">> npm ci --legacy-peer-deps"
npm ci --legacy-peer-deps --no-audit --no-fund

echo ">> prettier --write ."
npx prettier --write .

echo ">> tsc --noEmit"
npx tsc --noEmit

echo "Lint passed."
