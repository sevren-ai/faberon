# Install on a login node (no sudo)

Install Faberon's prerequisites on a shared cluster login node, with no root access. Everything installs under your home directory. For a machine you administer, see [install-workstation.md](install-workstation.md) instead. 

## 1. Install and run Postgres

Copy-paste the `install-postgres-no-sudo.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/install-postgres-no-sudo.sh) and execute it:

```bash
bash scripts/db/install-postgres-no-sudo.sh   # binaries + initdb + env file
```

The installer writes an env file to `~/.config/faberon/postgres.env` (or `$XDG_CONFIG_HOME/faberon/postgres.env`) recording the install paths and connection settings.

Now, also copy over the `start-postgres.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/start-postgres.sh), the `stop-postgres.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/stop-postgres.sh) and the `create-faberon-db` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/create-faberon-db.sh).
Start Postgres (each session, from the repo root), then create the databases once:

```bash
bash scripts/db/start-postgres.sh
bash scripts/db/create-faberon-db.sh         # creates faberon and faberon_test
```

The create script prints the `FABERON_DATABASE_URL` to export. It is also recorded in the env file `~/.config/faberon/postgres.env`.

To stop it: `bash scripts/db/stop-postgres.sh`.

Postgres does not start on boot, so start it after each login or reboot.

## 2. Set the environment

Refer to [the env guide](prepare-env.md).

## 3. Get Node

Faberon Chat needs Node 22.19 or newer, installed user-space since there is no sudo. 

One way, a plain tarball:

```bash
mkdir -p ~/.local/node
curl -fsSL https://nodejs.org/dist/v22.23.1/node-v22.23.1-linux-x64.tar.xz | tar -xJ --strip-components=1 -C ~/.local/node
export PATH="$HOME/.local/node/bin:$PATH"   # add to your shell profile
```

A version manager such as `nvm` or `mise` works too.

From here onwards, continue with the install/quickstart guide in the README.