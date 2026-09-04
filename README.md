# Faberon
Sevren's autonomous ML Research Harness

## Layout

- `packages/control-plane/`: the brain (Python, `uv`-managed, import name `faberon`)
- `docs/design/`: [system design](docs/design/design.md), [roadmap](docs/design/roadmap.md), [future ideas](docs/design/future.md), and one doc per release, starting at [v0.1.0](docs/design/v0.1.0.md)
- `CONTRIBUTING.md`: the process rules for every contributor, human or agent
- `AGENTS.md`: agent-specific rules (context loading, writing style), read first by any coding agent

The console (Pi extension, TypeScript) joins as a sibling package in upcoming work.

## Setup

The control plane stores its ledger in Postgres. You need a local Postgres to run Faberon (and to run the ledger tests).

On Fedora:

```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb          # creates the data dir with peer auth
sudo systemctl enable --now postgresql  # start it, and on boot
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
scripts/setup-db.sh                     # creates the faberon database
export FABERON_DATABASE_URL=postgres:///faberon
```

On Ubuntu:

```bash
sudo apt install postgresql postgresql-contrib   # package inits the cluster and starts the service
sudo -u postgres createuser --superuser "$USER"  # create a DB role matching your OS user
scripts/setup-db.sh                             # creates the faberon database
export FABERON_DATABASE_URL=postgres:///faberon
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). Data persists on disk under the Postgres data directory.
