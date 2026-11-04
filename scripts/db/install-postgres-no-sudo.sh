#!/usr/bin/env bash
# Install a Postgres server for Faberon without sudo (e.g. on a cluster login node).
#
# This only installs the server, it does not create the faberon database (`faberon init` does that).
#
# Optional env:
#   FABERON_PG_PREFIX   install root (default: $HOME/faberon/postgres)
#   FABERON_PG_PORT     listen port (default: derived from the username)
#   FABERON_PG_VERSION  binary release version (default: 16.15.0)

set -euo pipefail

prefix="${FABERON_PG_PREFIX:-$HOME/faberon/postgres}"
version="${FABERON_PG_VERSION:-16.15.0}"
target="x86_64-unknown-linux-gnu"
archive="postgresql-${version}-${target}.tar.gz"
url="https://github.com/theseus-rs/postgresql-binaries/releases/download/${version}/${archive}"
# DBOS runs CREATE EXTENSION "uuid-ossp". The theseus uuid-ossp.so needs
# libossp-uuid.so.16, which many login nodes do not ship. Vendor it.
ossp_deb_url="http://archive.ubuntu.com/ubuntu/pool/universe/o/ossp-uuid/libossp-uuid16_1.6.2-1.5build13_amd64.deb"

data="$prefix/data"
log_dir="$prefix/log"
run_dir="$prefix/run"
lib_dir="$prefix/lib"
env_file="${XDG_CONFIG_HOME:-$HOME/.config}/faberon/postgres.env"

ensure_libossp_uuid() {
    # uuid-ossp.so (shipped with the binaries) links against libossp-uuid.so.16.
    if [ -e "$lib_dir/libossp-uuid.so.16" ]; then
        echo ">> libossp-uuid.so.16 already in $lib_dir"
        return
    fi
    for candidate in \
        /lib/x86_64-linux-gnu/libossp-uuid.so.16 \
        /usr/lib/x86_64-linux-gnu/libossp-uuid.so.16 \
        /lib64/libossp-uuid.so.16; do
        if [ -e "$candidate" ]; then
            echo ">> copying $candidate into $lib_dir"
            cp -a "$candidate" "$lib_dir/"
            # Real file behind a symlink, if any.
            if [ -L "$candidate" ]; then
                real="$(readlink -f "$candidate")"
                cp -a "$real" "$lib_dir/"
            fi
            return
        fi
    done
    echo ">> downloading libossp-uuid (needed by uuid-ossp for DBOS)"
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap 'rm -rf "$tmp"' EXIT
    curl -fL --retry 3 -o "$tmp/libossp-uuid.deb" "$ossp_deb_url"
    dpkg-deb -x "$tmp/libossp-uuid.deb" "$tmp/root"
    so="$(find "$tmp/root" -name 'libossp-uuid.so.16' | head -1)"
    if [ -z "$so" ]; then
        echo "error: libossp-uuid.so.16 not found inside the downloaded package" >&2
        exit 1
    fi
    cp -a "$(dirname "$so")"/libossp-uuid.so.16* "$lib_dir/"
    rm -rf "$tmp"
    trap - EXIT
}

port_in_use() {
    # True if a TCP connect to the loopback port succeeds (IPv4 or IPv6).
    local port=$1
    if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
        return 0
    fi
    if (exec 3<>"/dev/tcp/::1/$port") 2>/dev/null; then
        return 0
    fi
    return 1
}

pick_free_port() {
    # Stable per-user base port, moved forward until one is free. Stays below
    # the Linux ephemeral range (32768+) so outbound connections cannot grab it.
    local base port i
    base=$(( 20000 + $(printf '%s' "$USER" | cksum | cut -d' ' -f1) % 10000 ))
    for i in $(seq 0 99); do
        port=$(( base + i ))
        if ! port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done
    echo "error: no free TCP port in range $base-$(( base + 99 ))" >&2
    return 1
}

port_from_conf() {
    # The port a previously initialised cluster is configured to listen on.
    sed -n 's/^[[:space:]]*port[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
        "$data/postgresql.conf" | tail -n 1
}

if [ "$(uname -m)" != "x86_64" ]; then
    echo "error: only x86_64 binaries are wired up (got $(uname -m))" >&2
    echo "set FABERON_PG_PREFIX to an existing install, or extend this script" >&2
    exit 1
fi

mkdir -p "$prefix" "$log_dir" "$run_dir" "$lib_dir"
# The unix socket is trust-authenticated, so only the owner may enter its directory.
chmod 0700 "$run_dir"
mkdir -p "$(dirname "$env_file")"

if [ ! -x "$prefix/bin/postgres" ]; then
    echo ">> downloading $archive"
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap 'rm -rf "$tmp"' EXIT
    curl -fL --retry 3 -o "$tmp/$archive" "$url"
    echo ">> unpacking into $prefix"
    tar -xzf "$tmp/$archive" -C "$tmp"
    # Archive root is postgresql-$version-$target/; move its contents into $prefix.
    src="$tmp/postgresql-${version}-${target}"
    # Copy rather than move across filesystems
    cp -a "$src"/. "$prefix"/
    rm -rf "$tmp"
    trap - EXIT
else
    echo ">> binaries already present at $prefix/bin"
fi

ensure_libossp_uuid

if [ ! -f "$data/PG_VERSION" ]; then
    if [ -n "${FABERON_PG_PORT:-}" ]; then
        port="$FABERON_PG_PORT"
        if port_in_use "$port"; then
            echo "error: FABERON_PG_PORT=$port is already taken on localhost" >&2
            echo "another Postgres may already listen there (issue #74); pick a different port" >&2
            exit 1
        fi
    else
        port="$(pick_free_port)"
    fi
    echo ">> initdb $data (port $port, scram-sha-256 for TCP)"
    # Random superuser password for TCP. The unix socket stays
    # trust-authenticated but sits in a 0700 directory only the owner can enter.
    password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    pwfile="$(mktemp)"
    # shellcheck disable=SC2064
    trap 'rm -f "$pwfile"' EXIT
    printf '%s\n' "$password" >"$pwfile"
    "$prefix/bin/initdb" \
        -D "$data" \
        --username="$USER" \
        --auth-local=trust \
        --auth-host=scram-sha-256 \
        --pwfile="$pwfile" \
        --no-instructions
    rm -f "$pwfile"
    trap - EXIT
    {
        echo
        echo "# Faberon no-sudo install overrides"
        echo "listen_addresses = 'localhost'"
        echo "port = $port"
        echo "unix_socket_directories = '$run_dir'"
        echo "unix_socket_permissions = 0700"
    } >>"$data/postgresql.conf"
    db_url="postgres://${USER}:${password}@localhost:${port}/faberon"
else
    echo ">> data directory already initialised at $data"
    port="$(port_from_conf)"
    if [ -z "$port" ]; then
        echo "error: could not read the port from $data/postgresql.conf" >&2
        exit 1
    fi
    if [ -n "${FABERON_PG_PORT:-}" ] && [ "$FABERON_PG_PORT" != "$port" ]; then
        echo ">> existing cluster keeps port $port from postgresql.conf; ignoring FABERON_PG_PORT=$FABERON_PG_PORT"
    fi
    # Reuse the URL (with its credentials) from the previous env file, if any.
    db_url=""
    if [ -f "$env_file" ]; then
        db_url="$(
            # shellcheck disable=SC1090
            source "$env_file" >/dev/null 2>&1 || true
            printf '%s' "${FABERON_PG_URL:-}"
        )"
    fi
    if [ -z "$db_url" ]; then
        db_url="postgres://localhost:${port}/faberon"
    fi
    if grep -qE '^[[:space:]]*host[[:space:]]+.*[[:space:]]trust[[:space:]]*$' "$data/pg_hba.conf"; then
        cat >&2 <<'EOF'
warning: this cluster predates the fix for issue #74 and still accepts
passwordless TCP connections (trust auth) from any user on this machine.
To harden it: stop Postgres, move the data directory aside, re-run this
installer for a fresh password-protected cluster, then recreate the databases.
EOF
    fi
fi

cat >"$env_file" <<EOF
# Generated by scripts/db/install-postgres-no-sudo.sh.
# Sourced by the Faberon Postgres scripts, not by your login shell.
# Contains the database password; keep it private (mode 0600).
export PATH="$prefix/bin:\$PATH"
export LD_LIBRARY_PATH="$lib_dir\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export FABERON_PG_PREFIX="$prefix"
export FABERON_PGDATA="$data"
export PGDATA="$data"
export PGHOST="$run_dir"
export PGPORT=$port
export FABERON_PG_URL="$db_url"
EOF
# The env file carries the database password.
chmod 0600 "$env_file"

cat <<EOF

Postgres (no-sudo install) is ready.

  install:  $prefix
  data:     $data
  port:     $port
  env file: $env_file

Connections:
  psql and the db scripts use the private unix socket in $run_dir (no password).
  Faberon connects over TCP with a password; FABERON_PG_URL in the env
  file carries it.

To start it, run start-postgres.sh. docs/install.md shows where to get it:

    bash ~/.local/bin/start-postgres.sh

Then set up Faberon (creates the database when it is missing):

    faberon init

To stop it:

    bash scripts/db/stop-postgres.sh

Note: PGDATA lives on the same filesystem as \$HOME. On login nodes that is
often a network FS (e.g. Weka). Fine for Faberon's small ledger; do not put
a heavy production DB here.
EOF
