# Install on a workstation (sudo available)

Run Faberon's brain and console on a machine you administer: a workstation, a provisioned GPU box, any host where you can install system packages. For a shared login node without sudo, see [install-login-node.md](install-login-node.md). To develop Faberon itself, see [install-developer.md](install-developer.md).

The brain stores its ledger in Postgres, serves the v0 API, and runs campaigns. The console is an optional Pi extension for operating campaigns from a chat session.

## 1. Install Postgres

On Fedora:

```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb          # creates the data dir with peer auth
sudo systemctl enable --now postgresql  # start it, and on boot
sudo -u postgres createuser --superuser "$USER"
```

On Ubuntu:

```bash
sudo apt install postgresql postgresql-contrib   # package inits the cluster and starts the service
sudo -u postgres createuser --superuser "$USER"
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). The system package runs Postgres as a background service that starts on boot, so there is nothing to start or stop by hand.

## 2. Create the databases

The database scripts live in the repo. Clone it once just for this step (a shallow clone is enough), or copy `scripts/db/` over:

```bash
git clone --depth 1 https://github.com/sevren-ai/faberon
cd faberon
bash scripts/db/create-faberon-db.sh   # creates faberon and faberon_test
export FABERON_DATABASE_URL=postgres:///faberon
```

## 3. Install and run the brain

Install the `faberon` command, then set the environment it needs:

```bash
uv tool install git+https://github.com/sevren-ai/faberon

export FABERON_SLURM_ACCOUNT=<account>
export FABERON_API_TOKEN=<random_token>
export FABERON_MODEL=openrouter:<provider>/<model>
export OPENROUTER_API_KEY=<key>
```

`FABERON_API_TOKEN` is mandatory: it guards the API on a shared host. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. For a local model server with an OpenAI-compatible API, use `FABERON_MODEL=openai:<model>` with `OPENAI_BASE_URL` and `OPENAI_API_KEY=local` instead.

Start the API:

```bash
faberon serve
```

It runs in the foreground, on `127.0.0.1:8000` by default (`FABERON_HOST`, `FABERON_PORT`). Run it inside `tmux` or `screen` so it survives your session.

Optional deployment knobs:

- `FABERON_SLURM_GPUS`: GPU count per job (default 1).
- `FABERON_SLURM_MAX_TIME`: walltime cap in minutes; can only lower a plan's walltime, never raise it.
- `FABERON_SLURM_OUTPUT`: Slurm `--output` path for job stdout/stderr.
- `FABERON_PROPOSER_TIMEOUT`: seconds for one proposer LLM call (default 600).
- `FABERON_NO_RECOVER`: serve the API without resuming pending workflows at startup. See [troubleshooting.md](troubleshooting.md#safe-restart-and-recovery).

## 4. Use it

The CLI reads `FABERON_API_TOKEN` and `FABERON_API_URL` (default `http://127.0.0.1:8000`):

```bash
faberon create plan.json     # submit a campaign
faberon list                 # all campaigns, oldest first
faberon show <id>            # one campaign's plan and status
faberon events <id> -f       # stream the ledger live
faberon cancel <id>          # request cancellation
```

## 5. The console (optional)

To operate campaigns from a Pi chat session instead of the CLI, install the console extension. Requires Node 22.19 or newer (`sudo dnf install nodejs22 npm` on Fedora, or your distro's equivalent) and the Pi CLI:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install git:github.com/sevren-ai/faberon@console-v0.1.0
export FABERON_API_TOKEN=<same token as the brain>
pi
```

Once published to npm, the console installs as `pi install npm:@faberon/console` instead (see the v0.3.0 design doc). The console and CLI speak to the same API; use whichever suits the moment.
