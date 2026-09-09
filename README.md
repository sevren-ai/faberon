# Faberon
Sevren's autonomous ML Research Harness

## Layout

- `packages/control-plane/`: the brain (Python, `uv`-managed, import name `faberon`)
- `docs/design/`: [system design](docs/design/design.md), [roadmap](docs/design/roadmap.md), [future ideas](docs/design/future.md), and one doc per release, starting at [v0.1.0](docs/design/v0.1.0.md)
- `CONTRIBUTING.md`: the process rules for every contributor, human or agent
- `AGENTS.md`: agent-specific rules (context loading, writing style), read first by any coding agent

The console (Pi extension, TypeScript) joins as a sibling package in upcoming work.

## Setup

The control plane stores its ledger in Postgres. Setup is two layers:

1. **Install a Postgres server** (once per machine).
2. **Create the `faberon` database** with `scripts/create-faberon-db.sh` (once per server, with Postgres running).

How you do step 1 depends on the machine. Run the `scripts/` commands from the Faberon repo root.

### Dev machine (system Postgres)

On Fedora:

```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb          # creates the data dir with peer auth
sudo systemctl enable --now postgresql  # start it, and on boot
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
scripts/create-faberon-db.sh
export FABERON_DATABASE_URL=postgres:///faberon
```

On Ubuntu:

```bash
sudo apt install postgresql postgresql-contrib   # package inits the cluster and starts the service
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
scripts/create-faberon-db.sh
export FABERON_DATABASE_URL=postgres:///faberon
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). Data persists on disk under the Postgres data directory.

### Login node (no sudo)

Login nodes typically have no working sudo. Install a personal Postgres instead of the system package.

Once:

```bash
scripts/install-postgres-no-sudo.sh     # binaries + initdb + env file
```

To start it (each session, from the repo root):

```bash
source ~/.config/faberon/postgres.env
pg_ctl -D "$FABERON_PGDATA" -l "$FABERON_PGDATA/../log/pg.log" start
```

Once (with Postgres running):

```bash
scripts/create-faberon-db.sh            # creates the Faberon database
```

To stop it:

```bash
pg_ctl -D "$FABERON_PGDATA" stop
```

PGDATA sits next to the binaries on your home filesystem. On many clusters that is a network FS (for example Weka); that is fine for Faberon's small ledger and DBOS state.

## Running the API

With Postgres up and `FABERON_DATABASE_URL` set, start the control plane:

```bash
export FABERON_SLURM_ACCOUNT=<account>
export FABERON_API_TOKEN=<random_token>
cd packages/control-plane
uv run uvicorn --factory faberon.api:create_app_slurm --host 127.0.0.1 --port 8000
```

`FABERON_API_TOKEN` is mandatory for the Slurm entrypoint. 

You can generate a random token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- `GET /healthz`: liveness check (no auth required)
- `POST /v0/campaigns`: accept a plan + command, append `campaign.created`, start `run_experiment`
- `GET /v0/campaigns/{id}`: ledger events for that campaign
- `GET /v0/events?after=0`: SSE ledger tail
