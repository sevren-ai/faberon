"""Operator configuration, shared by the CLI, the chat interface, and the server.

The TOML config file is written by ``faberon init`` and it's the only configuration
mechanism.
An ``[env]`` table in the file carries provider credentials. The server exports
these into its process at startup without overwriting variables that are already set.
"""

import json
import os
import secrets
import tempfile
import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_PATH = Path("~/.config/faberon/config.toml").expanduser()

# Built-in defaults for `faberon init`
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DB_URL = "postgres:///faberon"
DEFAULT_PROPOSER_TIMEOUT = 600.0
DEFAULT_STATE_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "faberon")


class ConfigError(RuntimeError):
    """The config file exists but cannot be parsed."""


def config_path() -> Path:
    """The config file path: ``$FABERON_CONFIG`` or the default location."""
    config_path = os.environ.get("FABERON_CONFIG") or _DEFAULT_CONFIG_PATH
    return Path(config_path).expanduser()


def load() -> dict[str, Any]:
    """The parsed config file. Empty dict when the file does not exist."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


def _get(key: str, raise_on_none: bool = False) -> Any:
    """One raw value from the config file, or None when the key is absent.
    If raise_on_none is set to True and the value is None/empty, raise a ConfigError."""
    value = load().get(key)
    if not value and raise_on_none:
        raise ConfigError(f"no {key} in the config file: run `faberon init`")
    return value


def database_url() -> str:
    """The Postgres connection URL."""
    return _get("database_url", raise_on_none=True)


def model() -> str:
    """The proposer's LLM, for example ``openrouter:provider/model``."""
    return _get("model", raise_on_none=True)


def host() -> str:
    """The address ``faberon serve`` binds to."""
    return _get("host", raise_on_none=True)


def port() -> int:
    """The port ``faberon serve`` binds to."""
    return int(_get("port", raise_on_none=True))


def proposer_timeout() -> float:
    """Timeout (seconds) for one proposer LLM call."""
    return float(_get("proposer_timeout", raise_on_none=True))


def state_dir() -> str:
    """The local executor's private state directory."""
    return _get("state_dir", raise_on_none=True)


def api_token(raise_on_none: bool = False) -> str | None:
    """The bearer token guarding the API; None leaves a local server unguarded."""
    return _get("api_token", raise_on_none=raise_on_none)


def executor() -> str | None:
    """Which executor runs jobs; None means autodetect."""
    return _get("executor")


def slurm_account(raise_on_none: bool = False) -> str | None:
    """The Slurm account to bill jobs to, or None for the local executor."""
    return _get("slurm_account", raise_on_none=raise_on_none)


def slurm_gpus(raise_on_none: bool = False) -> int | None:
    """GPU count per Slurm job, or None for the local executor."""
    value = _get("slurm_gpus", raise_on_none=raise_on_none)
    return int(value) if value is not None else None


def max_time() -> int | None:
    """The walltime cap in minutes, or None for no cap."""
    value = _get("max_time")
    return int(value) if value is not None else None


def api_url() -> str:
    """Where clients reach the server: ``api_url``, or derived from host/port."""
    url = _get("api_url")
    if url:
        return str(url).rstrip("/")
    return f"http://{host()}:{port()}"


def apply_env() -> None:
    """Export the config file's ``[env]`` table, keeping variables already set."""
    for key, value in load().get("env", {}).items():
        os.environ.setdefault(key, str(value))


def generate_token() -> str:
    """A fresh API token."""
    return secrets.token_urlsafe(32)


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write(path: Path, values: dict[str, Any], env: dict[str, str]) -> None:
    """Write the config file atomically, private to the user (mode 0600)."""
    lines = ["# Written by `faberon init`"]
    lines += [f"{key} = {_toml_value(value)}" for key, value in values.items()]
    if env:
        lines += ["", "[env]"] + [
            f"{key} = {json.dumps(value)}" for key, value in env.items()
        ]
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
