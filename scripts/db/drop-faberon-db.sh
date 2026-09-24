#!/usr/bin/env bash
# Drop the Faberon databases (main and test) from an already-running Postgres.
# This destroys all campaign and ledger data. It asks for confirmation first
# and refuses to run without an interactive terminal, so it cannot fire by
# accident from another script or CI.

set -euo pipefail

main_db="faberon"
dbs=("$main_db" "${main_db}_test")

# Source the no-sudo Postgres env if present (puts psql/dropdb on PATH, sets PGPORT).
if [ -f ~/.config/faberon/postgres.env ]; then
    # shellcheck disable=SC1091
    source ~/.config/faberon/postgres.env
fi

if ! command -v dropdb >/dev/null 2>&1; then
    echo "error: dropdb not found on PATH; install PostgreSQL (or source ~/.config/faberon/postgres.env)" >&2
    exit 1
fi

if [ ! -t 0 ]; then
    echo "error: stdin is not a terminal; refusing to drop databases without an interactive confirmation" >&2
    exit 1
fi

echo "This will permanently DROP these databases and all their campaign data: ${dbs[*]}"
read -r -p "Type 'drop' to confirm: " answer
if [ "$answer" != "drop" ]; then
    echo "aborted; nothing dropped"
    exit 0
fi

for db in "${dbs[@]}"; do
    if psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
        dropdb "$db"
        echo "dropped database '$db'"
    else
        echo "database '$db' does not exist; skipped"
    fi
done

echo "Done. Recreate them with scripts/db/create-faberon-db.sh"
