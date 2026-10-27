# Install on a workstation (sudo available)

Install Faberon's prerequisites on a machine you administer: a workstation, a provisioned GPU box, a Mac, any host where you can install system packages. For a shared login node without sudo, see [install-login-node.md](install-login-node.md) instead.

## 1. Install and run Postgres

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

On macOS:

Packages come from [Homebrew](https://brew.sh) and need no sudo. macOS has no Slurm, so Faberon runs jobs with the local executor.

```bash
brew install postgresql@17
brew services start postgresql@17                        # start it, and on login
export PATH="$(brew --prefix postgresql@17)/bin:$PATH"   # keg-only; add to your shell profile
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). The system package runs Postgres as a background service that starts on boot, so there is nothing to start or stop by hand.

### Create the databases

Copy-paste the `create-faberon-db.sh` [script](https://github.com/sevren-ai/faberon/blob/main/scripts/db/create-faberon-db.sh) and execute it:

```bash
bash scripts/db/create-faberon-db.sh   # creates faberon and faberon_test DBs
```

The script should print `FABERON_DATABASE_URL` that needs to be set in your env, e.g.:
```bash 
export FABERON_DATABASE_URL=postgres:///faberon
```

## 2. Set the environment

Refer to [the env guide](prepare-env.md).

## 3. Get node

Faberon Chat needs Node 22.19 or newer.

E.g. on fedora:

```bash
sudo dnf install nodejs npm
```

On macOS:

```bash
brew install node
```

## 4. Install Pi

Faberon Chat is a Pi extension, so install the Pi CLI. A system-wide Node has its global npm prefix outside your home, so this uses sudo:

```bash
sudo npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

On macOS, Homebrew's npm prefix is owned by your user, so drop the `sudo`.

From here onwards, continue with the install/quickstart guide in the README.