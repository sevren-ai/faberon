# Install on a login node (no sudo)

Run Faberon's brain and console on a shared cluster login node, with no root access. Everything installs under your home directory. For a machine you administer, see [install-workstation.md](install-workstation.md). To develop Faberon itself, see [install-developer.md](install-developer.md).

Two things to know up front:

- **Egress.** The login node needs outbound HTTPS to GitHub (installs), to npm if you install the console from the registry, and to your LLM provider. Compute nodes typically have no egress; the login node usually does. If it does not, install on a machine that does and copy the results over.
- **Shared host.** Other users share the node. `FABERON_API_TOKEN` is mandatory: it guards the API on localhost.

## 1. Install Postgres (no sudo)

Install a personal Postgres server with the repo's installer. Clone the repo once (a shallow clone is enough) or copy `scripts/db/` over:

```bash
git clone --depth 1 https://github.com/sevren-ai/faberon
cd faberon
bash scripts/db/install-postgres-no-sudo.sh   # binaries + initdb + env file
```

The installer writes an env file to `~/.config/faberon/postgres.env` (or `$XDG_CONFIG_HOME/faberon/postgres.env`) recording the install paths and connection settings. `scripts/db/start-postgres.sh` and `scripts/db/stop-postgres.sh` source it.

Start Postgres (each session, from the repo root), then create the databases once:

```bash
bash scripts/db/start-postgres.sh
bash scripts/db/create-faberon-db.sh         # creates faberon and faberon_test
export FABERON_DATABASE_URL=postgres:///faberon
```

To stop it: `bash scripts/db/stop-postgres.sh`.

PGDATA sits next to the binaries on your home filesystem. On many clusters that is a network FS (for example Weka); that is fine for Faberon's small ledger and DBOS state. Postgres does not start on boot here, so start it after each login or reboot (see [roadmap](design/roadmap.md) for the lifecycle open question).

## 2. Install and run the brain

```bash
uv tool install git+https://github.com/sevren-ai/faberon

export FABERON_SLURM_ACCOUNT=<account>
export FABERON_API_TOKEN=<random_token>
export FABERON_MODEL=openrouter:<provider>/<model>
export OPENROUTER_API_KEY=<key>
```

Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Start the API inside `tmux` or `screen` so it survives your SSH session:

```bash
tmux
faberon serve
```

It listens on `127.0.0.1:8000` by default (`FABERON_HOST`, `FABERON_PORT`). The optional knobs (`FABERON_SLURM_GPUS`, `FABERON_SLURM_MAX_TIME`, `FABERON_SLURM_OUTPUT`, `FABERON_PROPOSER_TIMEOUT`, `FABERON_NO_RECOVER`) are documented in [install-workstation.md](install-workstation.md#3-install-and-run-the-brain).

## 3. Use it

```bash
faberon create plan.json
faberon list
faberon events <id> -f
faberon cancel <id>
```

## 4. The console (optional)

The console needs Node 22.19 or newer, installed user-space since there is no sudo. One way, a plain tarball:

```bash
mkdir -p ~/.local/node
curl -fsSL https://nodejs.org/dist/v22.23.1/node-v22.23.1-linux-x64.tar.xz | tar -xJ --strip-components=1 -C ~/.local/node
export PATH="$HOME/.local/node/bin:$PATH"   # add to your shell profile
```

(A version manager such as `nvm` or `mise` works too.) With Node on `PATH`, npm's global prefix is the user-space install, so no sudo is needed for the Pi CLI:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install git:github.com/sevren-ai/faberon@console-v0.1.0
export FABERON_API_TOKEN=<same token as the brain>
pi
```

Once published to npm, the console installs as `pi install npm:@faberon/console` instead (see the v0.3.0 design doc).
