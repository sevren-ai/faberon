#!/usr/bin/env bash
# Drop the Faberon database from an already-running Postgres.
# This destroys all campaign and ledger data. It asks for confirmation first
# and refuses to run without an interactive terminal, so it cannot fire by
# accident from another script or CI.

set -euo pipefail

db="faberon"

# Source the no-sudo Postgres env if present (puts psql/dropdb on PATH, sets PGHOST/PGPORT).
env_file="${XDG_CONFIG_HOME:-$HOME/.config}/faberon/postgres.env"
if [ -f "$env_file" ]; then
    # shellcheck disable=SC1090
    source "$env_file"
fi

if ! command -v dropdb >/dev/null 2>&1; then
    echo "error: dropdb not found on PATH; install PostgreSQL (or source ~/.config/faberon/postgres.env)" >&2
    exit 1
fi

if [ ! -t 0 ]; then
    echo "error: stdin is not a terminal; refusing to drop the database without an interactive confirmation" >&2
    exit 1
fi

echo "This will permanently DROP the database '$db' and all its campaign data"
read -r -p "Type 'drop' to confirm: " answer
if [ "$answer" != "drop" ]; then
    echo "aborted; nothing dropped"
    exit 0
fi

if psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    dropdb "$db"
    echo "dropped database '$db'"
else
    echo "database '$db' does not exist; nothing to drop"
fi

echo "Done. If you want to recreate the faberon database, run \`faberon init\`"
