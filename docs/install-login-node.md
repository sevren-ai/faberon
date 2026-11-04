# Install on a login node (no sudo)

Install Faberon's prerequisites on a shared cluster login node, with no root access. Everything installs under your home directory. For a machine you administer, see [install-workstation.md](install-workstation.md) instead. 

## 1. Install and run Postgres

Copy-paste the `install-postgres-no-sudo.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/install-postgres-no-sudo.sh) and execute it:

```bash
bash scripts/db/install-postgres-no-sudo.sh   # binaries + initdb + env file
```

The installer writes an env file to `~/.config/faberon/postgres.env` (or `$XDG_CONFIG_HOME/faberon/postgres.env`) recording the install paths and connection settings.

- The TCP port is derived from your username and probed free at install time, so two users on one node do not collide on one fixed port. Set `FABERON_PG_PORT` to choose your own.

Now, also copy over the `start-postgres.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/start-postgres.sh) and the `stop-postgres.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/stop-postgres.sh).
Start Postgres (each session, from the repo root):

```bash
bash scripts/db/start-postgres.sh
```

Postgres does not start on boot, so start it after each login or reboot.

To stop it after a session, you can run (but don't do this now):

```bash
bash scripts/db/stop-postgres.sh
```

## 2. Configure Faberon

Refer to [the configuration guide](configure-faberon.md).

## 3. Get Node

This is only required if you want to use Faberon Chat. Faberon Chat needs Node 22.19 or newer, installed user-space since there is no sudo. 

One way, a plain tarball:

```bash
mkdir -p ~/.local/node
curl -fsSL https://nodejs.org/dist/v22.23.1/node-v22.23.1-linux-x64.tar.xz | tar -xJ --strip-components=1 -C ~/.local/node
export PATH="$HOME/.local/node/bin:$PATH"   # add to your shell profile
```

A version manager such as `nvm` or `mise` works too.

## 4. Install Pi

This is only required if you want to use Faberon Chat. Faberon Chat is a Pi extension, so install the Pi CLI. The user-space Node above has its global npm prefix inside your home, so no sudo is needed:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

## 5. Get uv

The brain is installed with `uv`, a single static binary that needs no sudo:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs into ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"              # add to your shell profile
```

The brain requires Python 3.14; uv installs a managed one on first use if the system Python is older.

From here onwards, continue with the install/quickstart guide in the README.