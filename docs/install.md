# Install Faberon

This guide installs Faberon and its prerequisites. Pick your track for steps 1-3:

- **Track A: workstation.** A machine you administer: a workstation, a provisioned GPU box, a Mac. You can install system packages.
- **Track B: login node.** A shared cluster login node without root access. Everything installs under your home directory.

Each track installs the prerequisites. Three shared steps (4-6) follow: [install the Faberon brain](#4-install-the-faberon-brain), [configure Faberon](#5-configure-faberon), and optionally [install Faberon Chat](#6-install-faberon-chat).

## Track A: workstation

### A1. Install and run Postgres

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

On macOS, packages come from [Homebrew](https://brew.sh) and need no sudo:

```bash
brew install postgresql@17
brew services start postgresql@17                        # start it, and on login
export PATH="$(brew --prefix postgresql@17)/bin:$PATH"   # keg-only; add to your shell profile
```

The default database URL `postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). The system package runs Postgres as a background service that starts on boot, so there is nothing to start or stop by hand.

### A2. Install uv

On Linux, use the installer (no sudo):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs into ~/.local/bin
```

On macOS:

```bash
brew install uv
```

The brain requires Python 3.14; uv installs a managed one on first use if the system Python is older.

### A3. Install Node (optional)

Only needed if you want the chat interface. Faberon Chat needs Node 22.19 or newer.

On Fedora:

```bash
sudo dnf install nodejs npm
```

On macOS:

```bash
brew install node
```

Continue with [Install the Faberon brain](#4-install-the-faberon-brain).

## Track B: login node (no sudo)

### B1. Install and run Postgres

Download and run the installer:

```bash
curl -fsSLO https://raw.githubusercontent.com/sevren-ai/faberon/main/scripts/db/install-postgres-no-sudo.sh
bash install-postgres-no-sudo.sh   # binaries + initdb + env file
```

If you already cloned the repo, the same script is at `scripts/db/install-postgres-no-sudo.sh`.

The installer writes an env file to `~/.config/faberon/postgres.env` (or `$XDG_CONFIG_HOME/faberon/postgres.env`) recording the install paths and connection settings. The TCP port is derived from your username and probed free at install time, so two users on one node do not collide on one fixed port. Set `FABERON_PG_PORT` to choose your own.

Download the start and stop scripts into `~/.local/bin` and start Postgres:

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/sevren-ai/faberon/main/scripts/db/start-postgres.sh -o ~/.local/bin/start-postgres.sh
curl -fsSL https://raw.githubusercontent.com/sevren-ai/faberon/main/scripts/db/stop-postgres.sh -o ~/.local/bin/stop-postgres.sh
bash ~/.local/bin/start-postgres.sh
```

Postgres does not start on boot, so start it after each login or reboot. To stop it at the end of a session (but not now):

```bash
bash ~/.local/bin/stop-postgres.sh
```

### B2. Install uv

uv is a single static binary that needs no sudo:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs into ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"              # add to your shell profile
```

The brain requires Python 3.14; uv installs a managed one on first use if the system Python is older.

### B3. Install Node (optional)

Only needed if you want the chat interface. Faberon Chat needs Node 22.19 or newer, installed in user space since there is no sudo:

```bash
mkdir -p ~/.local/node
curl -fsSL https://nodejs.org/dist/v22.23.1/node-v22.23.1-linux-x64.tar.xz | tar -xJ --strip-components=1 -C ~/.local/node
export PATH="$HOME/.local/node/bin:$PATH"   # add to your shell profile
```

A version manager such as `nvm` or `mise` works too.

## 4. Install the Faberon brain

Both tracks converge here. Install the brain from PyPI:

```bash
uv tool install faberon
```

Or from source:

```bash
git clone https://github.com/sevren-ai/faberon
cd faberon
uv tool install packages/brain
```

`uv tool` puts the `faberon` command on your `PATH`, so it works from any shell, including a fresh `tmux` session.

## 5. Configure Faberon

Run the setup wizard:

```bash
faberon init
```

The wizard generates the API token, asks for the LLM model and, on a Slurm cluster, the account. It then writes `~/.config/faberon/config.toml` with mode `0600`. The wizard requires a running Postgres and creates the `faberon` database. On the login-node track it reads the connection settings from `~/.config/faberon/postgres.env` and offers the right `database_url` as the default.

[configure-faberon.md](configure-faberon.md) has the full settings reference.

## 6. Install Faberon Chat (optional)

Skip this section if you do not want the chat interface. It needs Node 22.19 or newer (step A3 or B3 of your track).

Faberon Chat is a Pi extension. Install the Pi CLI and register the extension from npm:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install npm:@faberon/chat
```

Or from a source clone:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install ./packages/chat   # run from the repo root
```

With a system-wide Node (Track A on Linux), the global npm prefix is outside your home, so run the `npm install -g` command with `sudo`. Homebrew Node on macOS and the user-space Node from Track B need no sudo.

Then continue with the [quickstart](../README.md#quickstart).
