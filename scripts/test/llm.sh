#!/usr/bin/env bash
# Run the LLM integration tests. These call the real model configured in config file, so they require network access to the
# provider.

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
pkg="$repo_root/packages/brain"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

if ! uv run python -c "from faberon import config; raise SystemExit(0 if config.get('model') else 1)"; then
    echo "error: no model in the config file: run \`faberon init\`" >&2
    exit 1
fi

echo ">> pytest -m llm"
uv run pytest -rs -m llm

echo "LLM integration tests passed."
