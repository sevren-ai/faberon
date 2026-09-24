# Faberon
Sevren's autonomous ML Research Harness

## Layout

- `packages/control-plane/`: the brain (Python, `uv`-managed, import name `faberon`)
- `docs/design/`: [system design](docs/design/design.md), [roadmap](docs/design/roadmap.md), [future ideas](docs/design/future.md), and one doc per release (shipped releases in [archive/](docs/design/archive/))
- `CONTRIBUTING.md`: the process rules for every contributor, human or agent
- `AGENTS.md`: agent-specific rules (context loading, writing style), read first by any coding agent

The console (Pi extension, TypeScript) joins as a sibling package in upcoming work.

## Setup

The control plane stores its ledger in Postgres. Setup is two layers:

1. **Install a Postgres server** (once per machine).
2. **Create the databases** with `scripts/db/create-faberon-db.sh` (once per server, with Postgres running). This creates `faberon` for the control plane and `faberon_test` for the test suite.

How you do step 1 depends on the machine. Run the `scripts/` commands from the Faberon repo root.

### Dev machine (system Postgres)

On Fedora:

```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb          # creates the data dir with peer auth
sudo systemctl enable --now postgresql  # start it, and on boot
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
bash scripts/db/create-faberon-db.sh
export FABERON_DATABASE_URL=postgres:///faberon
```

On Ubuntu:

```bash
sudo apt install postgresql postgresql-contrib   # package inits the cluster and starts the service
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
bash scripts/db/create-faberon-db.sh
export FABERON_DATABASE_URL=postgres:///faberon
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). Data persists on disk under the Postgres data directory.

The system package runs Postgres as a background service that starts on boot, so there is nothing to start or stop by hand. Do not use `scripts/db/start-postgres.sh` or `scripts/db/stop-postgres.sh` here; those are for the no-sudo install below.

### Login node (no sudo)

Login nodes typically have no working sudo. Install a personal Postgres instead of the system package.

Once:

```bash
bash scripts/db/install-postgres-no-sudo.sh  # binaries + initdb + env file
```

The installer writes an env file to `~/.config/faberon/postgres.env` (or `$XDG_CONFIG_HOME/faberon/postgres.env`). It records the install paths and connection settings. `scripts/db/start-postgres.sh` and `scripts/db/stop-postgres.sh` source this file.

To start the postgres (each session, from the repo root):

```bash
bash scripts/db/start-postgres.sh
```

Once (with Postgres running):

```bash
bash scripts/db/create-faberon-db.sh         # creates the faberon and faberon_test databases
```

To stop it:

```bash
bash scripts/db/stop-postgres.sh
```

PGDATA sits next to the binaries on your home filesystem. On many clusters that is a network FS (for example Weka); that is fine for Faberon's small ledger and DBOS state.

## Running the API

Ensure the following vars are set:

```bash
export FABERON_SLURM_ACCOUNT=<account>
export FABERON_API_TOKEN=<random_token>
```

`FABERON_API_TOKEN` is mandatory for the Slurm entrypoint.

Then, set the model's parameters, either using OpenRouter:

```bash
export FABERON_MODEL=openrouter:<provider>/<model>
export OPENROUTER_API_KEY=<key>
```

Or a local server with an OpenAI-compatible API:

```bash
export FABERON_MODEL=openai:<model>
export OPENAI_BASE_URL=http://localhost:<port>/v1
export OPENAI_API_KEY=local
```

The OpenAI client requires a key value. A local server may ignore it.

Optional deployment-side knobs:

- `FABERON_SLURM_GPUS`: GPU count per job (default 1).
- `FABERON_SLURM_MAX_TIME`: walltime cap in minutes. Each job's walltime comes from its campaign plan; this cap can only lower it, never raise it. Set it to protect the cluster from runaway jobs.
- `FABERON_SLURM_OUTPUT`: Slurm `--output` path for job stdout/stderr.
- `FABERON_PROPOSER_TIMEOUT`: bound in seconds on one proposer LLM call. On expiry the call fails. Defaults to 600 if not set.

You can generate a random token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Now start the control plane, either by running it directly: 

```bash
cd packages/control-plane
uv run uvicorn --factory faberon.api:create_app_slurm --host 127.0.0.1 --port 8000
```

Or install the `faberon` command once and run it from anywhere:

```bash
uv tool install packages/control-plane
faberon
```

All `/v0/*` routes require `Authorization: Bearer $FABERON_API_TOKEN`.

- `GET /healthz`: liveness check (no auth required)
- `POST /v0/campaigns`: accept a plan + command, append `campaign.created`, start the campaign workflow
- `GET /v0/campaigns`: list all campaign records, oldest first
- `POST /v0/campaigns/{id}/cancel`: append `cancel.requested`, signal the workflow to stop at its next decision boundary
- `GET /v0/campaigns/{id}`: the campaign record (plan, workflow ID, creation time)
- `GET /v0/campaigns/{id}/events?after=0`: SSE ledger tail for that campaign
- `GET /v0/campaigns/{id}/events.jsonl?after=0`: bounded snapshot, one JSON event per line
