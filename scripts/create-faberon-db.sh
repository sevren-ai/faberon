#!/usr/bin/env bash
# Create the Faberon databases inside an already-running Postgres: the main
# database for the control plane and a test database for the test suite.
# Postgres itself must already be installed and started (see README).

set -euo pipefail

main_db="faberon"
dbs=("$main_db" "${main_db}_test")

# Source the no-sudo Postgres env if present (puts psql on PATH, sets PGPORT).
if [ -f ~/.config/faberon/postgres.env ]; then
    # shellcheck disable=SC1091
    source ~/.config/faberon/postgres.env
fi

echo ">> checking postgres"
if ! command -v psql >/dev/null 2>&1; then
    echo "error: psql not found on PATH; install PostgreSQL (or source ~/.config/faberon/postgres.env)" >&2
    exit 1
fi

for db in "${dbs[@]}"; do
    echo ">> createdb $db"
    if psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
        echo "database '$db' already exists"
    else
        createdb "$db"
        echo "created database '$db'"
    fi
done

if [ -z "${FABERON_DATABASE_URL:-}" ]; then
    if [ -n "${PGPORT:-}" ]; then
        url="postgres://localhost:${PGPORT}/$main_db"
    else
        url="postgres:///$main_db"
    fi
    cat <<EOF

Databases ready. Export the connection URL for Faberon:

    export FABERON_DATABASE_URL=$url
EOF
fi
