#!/usr/bin/env bash
# Run the on-cluster Slurm integration tests. These submit real jobs to Slurm,
# so they require a login node with sbatch on PATH and opt-in env vars.
#
# Required env:
#   FABERON_SLURM_ACCOUNT   Slurm account to bill jobs to.

set -euo pipefail

if [ -z "${FABERON_SLURM_ACCOUNT:-}" ]; then
    echo "error: set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to" >&2
    exit 1
fi

# Resolve the repo root from the script location so it works from any cwd.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
pkg="$repo_root/packages/control-plane"

cd "$pkg"

echo ">> uv sync --locked"
uv sync --locked

echo ">> pytest -m slurm"
FABERON_SLURM_INTEGRATION=1 uv run pytest -rs -m slurm

echo "Slurm integration tests passed."
