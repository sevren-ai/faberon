#!/usr/bin/env bash
# Start the Postgres server installed by install-postgres-no-sudo.sh.

set -euo pipefail

source ~/.config/faberon/postgres.env
pg_ctl -D "$FABERON_PGDATA" -l "$FABERON_PGDATA/../log/pg.log" start
