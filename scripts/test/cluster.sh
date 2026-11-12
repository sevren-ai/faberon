#!/usr/bin/env bash
# Run on a Slurm login node the tests CI cannot: Slurm job-submission tests,
# LLM tests, and the CLI tests that need sbatch on PATH. This is the run every PR
# must paste into its description.
#
# Required: `slurm_account` and `model` in the Faberon config file,
# plus the provider key in its [env] table

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
pkg="$repo_root/packages/brain"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

for key in slurm_account model; do
    if ! uv run python -c "from faberon import config; raise SystemExit(0 if config.load().get('$key') else 1)"; then
        echo "error: no $key in the config file: run \`faberon init\`" >&2
        exit 1
    fi
done

# Compute nodes cannot see the login node's /tmp, so use the shared home.
# pytest wipes this directory on each run.
basetemp="${XDG_CACHE_HOME:-$HOME/.cache}/faberon-pytest"

echo ">> pytest -m 'slurm or llm or sbatch'"
FABERON_SLURM_INTEGRATION=1 uv run pytest -rs -m "slurm or llm or sbatch" --basetemp="$basetemp"

echo "Cluster tests passed."
