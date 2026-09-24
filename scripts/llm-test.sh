#!/usr/bin/env bash
# Run the LLM integration tests. These call the real model configured in
# FABERON_MODEL, so they require network access to the provider and opt-in
# env vars.
#
# Required env:
#   FABERON_MODEL         model string, e.g. openrouter:<provider>/<model>
#   provider key          OPENROUTER_API_KEY or OPENAI_API_KEY, matching the
#                         FABERON_MODEL prefix (see README.md).

set -euo pipefail

if [ -z "${FABERON_MODEL:-}" ]; then
    echo "error: set FABERON_MODEL to the model to test against" >&2
    exit 1
fi

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
pkg="$repo_root/packages/control-plane"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

echo ">> pytest -m llm"
uv run pytest -rs -m llm

echo "LLM integration tests passed."
