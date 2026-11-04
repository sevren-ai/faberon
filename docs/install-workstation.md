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

Packages come from [Homebrew](https://brew.sh) and need no sudo.

```bash
brew install postgresql@17
brew services start postgresql@17                        # start it, and on login
export PATH="$(brew --prefix postgresql@17)/bin:$PATH"   # keg-only; add to your shell profile
```

`postgres:///faberon` connects over the local unix socket using peer auth (you are authenticated as your OS user, no password, no network). The system package runs Postgres as a background service that starts on boot, so there is nothing to start or stop by hand.

## 2. Configure Faberon

Refer to [the configuration guide](configure-faberon.md).

## 3. Get node

This is only required if you want to use Faberon Chat. Faberon Chat needs Node 22.19 or newer.

E.g. on fedora:

```bash
sudo dnf install nodejs npm
```

On macOS:

```bash
brew install node
```

## 4. Install Pi

This is only required if you want to use Faberon Chat. Faberon Chat is a Pi extension, so install the Pi CLI. A system-wide Node has its global npm prefix outside your home, so this uses sudo:

```bash
sudo npm install -g --ignore-scripts @earendil-works/pi-coding-agent # drop `sudo` on macOS
```

## 5. Get uv

The brain is installed with `uv`. If you don't have it installed:

On macOS:

```bash
brew install uv
```

On Linux, use the installer (no sudo):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs into ~/.local/bin
```

The brain requires Python 3.14; uv installs a managed one on first use if the system Python is older.

From here onwards, continue with the install/quickstart guide in the README.