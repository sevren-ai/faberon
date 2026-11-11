#!/usr/bin/env bash
# Start the Postgres server installed by install-postgres-no-sudo.sh.
# Only for the no-sudo install; a system Postgres is managed with systemctl.

set -euo pipefail

env_file="${XDG_CONFIG_HOME:-$HOME/.config}/faberon/postgres.env"
if [ ! -f "$env_file" ]; then
    echo "error: $env_file not found" >&2
    echo "this script only manages a personal Postgres installed by scripts/db/install-postgres-no-sudo.sh" >&2
    echo "if you installed Postgres with your system package manager (dnf/apt), it is already running as a system service" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$env_file"

if pg_ctl -D "$FABERON_PGDATA" status >/dev/null 2>&1; then
    if PGCONNECT_TIMEOUT=5 psql -d postgres -tAc 'SELECT 1' >/dev/null 2>&1; then
        echo "postgres is already running (port $PGPORT)"
        exit 0
    fi
    # The postmaster is alive but not answering. Seen on login nodes after
    # logout, where systemd-logind's RemoveIPC=yes deleted its shared memory
    # segments. Restart it.
    echo "postgres is running but not answering connections; restarting it"
    pg_ctl -D "$FABERON_PGDATA" stop -m fast
fi

log_file="$FABERON_PG_PREFIX/log/pg.log"
if ! pg_ctl -D "$FABERON_PGDATA" -l "$log_file" start; then
    echo "error: postgres failed to start; the real error is in the server log:" >&2
    echo "    tail -20 $log_file" >&2
    if [ -f "$log_file" ] && tail -20 "$log_file" | grep -qi "address already in use"; then
        echo "hint: port $PGPORT is already taken, possibly by another user's Postgres on a" >&2
        echo "shared node (see https://github.com/sevren-ai/faberon/issues/74)." >&2
        echo "check with: ss -tln | grep $PGPORT" >&2
    fi
    exit 1
fi
