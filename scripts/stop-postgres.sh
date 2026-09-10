#!/usr/bin/env bash
# Stop the Postgres server started by start-postgres.sh.

set -euo pipefail

source ~/.config/faberon/postgres.env
pg_ctl -D "$FABERON_PGDATA" stop
