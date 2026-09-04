#!/usr/bin/env bash
# Create the Faberon Postgres database for local development.
#
# Assumes a local PostgreSQL install where the current OS user can create
# databases (peer/trust auth, the default on a dev machine). The login-node
# userspace install path comes with the workflow PR.
#
# Usage: scripts/setup-db.sh

set -euo pipefail

db="faberon"

echo ">> checking postgres"
if ! command -v psql >/dev/null 2>&1; then
    echo "error: psql not found on PATH; install PostgreSQL client tools" >&2
    exit 1
fi

echo ">> createdb $db"
if psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    echo "database '$db' already exists"
else
    createdb "$db"
    echo "created database '$db'"
fi

cat <<EOF

Database ready. Export the connection URL for Faberon:

    export FABERON_DATABASE_URL=postgres:///$db
EOF
