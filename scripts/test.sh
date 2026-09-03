#!/usr/bin/env bash
# Run the test suite CI runs, locally. Exits non-zero on failure.
# Mirrors .github/workflows/test.yml.
#
# Usage: scripts/test.sh

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
pkg="$repo_root/packages/control-plane"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

echo ">> pytest"
uv run pytest

echo "Tests passed."
