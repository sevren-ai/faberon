#!/usr/bin/env bash
# Run all integration tests against real infrastructure: Slurm jobs and the
# configured LLM. Combines slurm.sh and llm.sh in one pytest run.
#
# Required env:
#   FABERON_SLURM_ACCOUNT Slurm account to bill jobs to.
#   FABERON_MODEL         model string, e.g. openrouter:<provider>/<model>
#   provider key          OPENROUTER_API_KEY or OPENAI_API_KEY, matching the
#                         FABERON_MODEL prefix (see README.md).

set -euo pipefail

if [ -z "${FABERON_SLURM_ACCOUNT:-}" ]; then
    echo "error: set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to" >&2
    exit 1
fi
if [ -z "${FABERON_MODEL:-}" ]; then
    echo "error: set FABERON_MODEL to the model to test against" >&2
    exit 1
fi

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
pkg="$repo_root/packages/brain"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

echo ">> pytest -m 'slurm or llm'"
FABERON_SLURM_INTEGRATION=1 uv run pytest -rs -m "slurm or llm"

echo "Integration tests passed."
