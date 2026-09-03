#!/usr/bin/env bash
# Run the lint checks CI runs, locally. Exits non-zero on the first failure.
# Mirrors .github/workflows/lint.yml.
#
# Usage: scripts/lint.sh

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
pkg="$repo_root/packages/control-plane"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

echo ">> ruff format --check src tests"
uv run ruff format --check src tests

echo ">> ruff check src tests"
uv run ruff check src tests

echo ">> ty check src tests"
uv run ty check src tests

echo "Lint passed."
