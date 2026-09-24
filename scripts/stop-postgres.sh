#!/usr/bin/env bash
# Stop the Postgres server started by start-postgres.sh.
# Only for the no-sudo install; a system Postgres is managed with systemctl.

set -euo pipefail

env_file="${XDG_CONFIG_HOME:-$HOME/.config}/faberon/postgres.env"
if [ ! -f "$env_file" ]; then
    echo "error: $env_file not found" >&2
    echo "this script only manages a personal Postgres installed by scripts/install-postgres-no-sudo.sh" >&2
    echo "if you installed Postgres with your system package manager (dnf/apt), it runs as a system service; stop it with: sudo systemctl stop postgresql" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$env_file"
pg_ctl -D "$FABERON_PGDATA" stop
