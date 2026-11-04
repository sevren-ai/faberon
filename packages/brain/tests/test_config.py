"""Tests for the persistent config file (faberon.config)."""

import os
import stat

import pytest

from faberon import config


@pytest.fixture
def config_file(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point FABERON_CONFIG at a path in tmp_path; return that path."""
    path = tmp_path / "config.toml"
    monkeypatch.setenv("FABERON_CONFIG", str(path))
    return path


def test_config_path_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FABERON_CONFIG", raising=False)
    assert config.config_path() == config._DEFAULT_CONFIG_PATH


def test_config_path_env_override(config_file):
    assert config.config_path() == config_file


def test_load_missing_file(config_file):
    assert config.load() == {}


def test_load_invalid_toml(config_file):
    config_file.write_text("this is = = not toml\n")
    with pytest.raises(config.ConfigError, match="invalid config"):
        config.load()


def test_get_reads_the_file(config_file):
    assert config._get("api_token") is None

    config_file.write_text('api_token = "from-file"\n')
    assert config._get("api_token") == "from-file"


def test_get_ignores_env_vars(config_file, monkeypatch: pytest.MonkeyPatch):
    """The file is the only source: a FABERON_* env var does not override it."""
    config_file.write_text('api_token = "from-file"\n')
    monkeypatch.setenv("FABERON_API_TOKEN", "from-env")
    assert config._get("api_token") == "from-file"


def test_api_url(config_file):
    """api_url comes from the key, or derives from host and port."""
    with pytest.raises(config.ConfigError):
        config.api_url()  # no api_url, host, or port in the file
    config_file.write_text('host = "127.0.0.1"\nport = 9100\n')
    assert config.api_url() == "http://127.0.0.1:9100"
    config_file.write_text('api_url = "http://elsewhere:9000/"\nport = 9100\n')
    assert config.api_url() == "http://elsewhere:9000"


def test_get_keeps_toml_types(config_file):
    config_file.write_text('port = 9000\nhost = "0.0.0.0"\n')
    assert config.port() == 9000
    assert config.host() == "0.0.0.0"


def test_required_accessors_raise(config_file):
    """Mandatory settings raise a clear error when the file lacks them."""
    for accessor in (
        config.database_url,
        config.model,
        config.host,
        config.port,
        config.proposer_timeout,
        config.state_dir,
    ):
        with pytest.raises(config.ConfigError, match="run `faberon init`"):
            accessor()


def test_optional_accessors_return_none(config_file):
    """Optional settings return None; absence is the value, not a default."""
    assert config.api_token() is None
    assert config.executor() is None
    assert config.slurm_account() is None
    assert config.slurm_gpus() is None
    assert config.max_time() is None


def test_apply_env(config_file, monkeypatch: pytest.MonkeyPatch):
    """The [env] table fills in unset variables and leaves set ones alone."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    config_file.write_text(
        '[env]\nOPENROUTER_API_KEY = "sk-or"\nOPENAI_API_KEY = "from-file"\n'
    )
    config.apply_env()
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or"
    assert os.environ["OPENAI_API_KEY"] == "already-set"


def test_write_roundtrip_and_permissions(config_file):
    config.write(
        config_file,
        {
            "api_token": "tok:en",
            "database_url": "postgres:///faberon",
            "model": "openrouter:x/y",
            "executor": "slurm",
            "slurm_gpus": 2,
        },
        {"OPENROUTER_API_KEY": "sk-or"},
    )
    mode = stat.S_IMODE(config_file.stat().st_mode)
    assert mode == 0o600
    loaded = config.load()
    assert loaded["api_token"] == "tok:en"
    assert loaded["slurm_gpus"] == 2
    assert loaded["env"] == {"OPENROUTER_API_KEY": "sk-or"}


def test_write_creates_private_parent(tmp_path):
    path = tmp_path / "newdir" / "config.toml"
    config.write(path, {"api_token": "tok"}, {})
    mode = stat.S_IMODE(path.parent.stat().st_mode)
    assert mode == 0o700
