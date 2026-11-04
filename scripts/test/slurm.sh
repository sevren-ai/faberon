#!/usr/bin/env bash
# Run the on-cluster Slurm integration tests. These submit real jobs to Slurm,
# so they require a login node with sbatch on PATH.
#
# Required: `slurm_account` in the Faberon config file.

set -euo pipefail

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
pkg="$repo_root/packages/brain"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

if ! uv run python -c "from faberon import config; raise SystemExit(0 if config.load().get('slurm_account') else 1)"; then
    echo "error: no slurm_account in the config file: run \`faberon init\`" >&2
    exit 1
fi

# Compute nodes cannot see the login node's /tmp, so use the shared home.
# pytest wipes this directory on each run.
basetemp="${XDG_CACHE_HOME:-$HOME/.cache}/faberon-pytest"

echo ">> pytest -m slurm"
FABERON_SLURM_INTEGRATION=1 uv run pytest -rs -m slurm --basetemp="$basetemp"

echo "Slurm integration tests passed."
