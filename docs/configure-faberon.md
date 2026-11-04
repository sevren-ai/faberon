## Faberon configuration

Faberon keeps its settings in one config file, written by the setup wizard.

```bash
faberon init
```

The wizard generates the API token, asks for the LLM model and, on a Slurm cluster, the account. It then writes `~/.config/faberon/config.toml` with mode `0600`. Re-run `faberon init` after every upgrade to keep the configuration up-to-date.

The wizard requires a running Postgres. It creates the `faberon` database.

If you want to change the location of this file, you can set an env var `FABERON_CONFIG`.

### Settings

| Key | Meaning |
|---|---|
| `model` | LLM for the proposer, for example `openrouter:<provider>/<model>`. |
| `executor` | `slurm` or `local`. Default: `slurm` when `sbatch` is on `PATH`, else `local`. |
| `slurm_account` | Slurm account to bill jobs to. Required with the Slurm executor. |
| `slurm_gpus` | GPU count per job (default 1). Slurm executor only. |
| `host` | Address `faberon serve` binds to (default `127.0.0.1`). |
| `port` | Port `faberon serve` binds to (default `8000`). |
| `api_url` | Where clients reach the server. Default: derived from `host` and `port`, so it cannot drift from them. Only set it for remote access. |
| `api_token` | Bearer token guarding the API. |
| `database_url` | Postgres connection URL. |


### Provider keys

An `[env]` table in the config file holds credentials for your LLM provider. `faberon init` fills this in for OpenRouter and OpenAI-compatible providers:

```toml
[env]
OPENROUTER_API_KEY = "<key>"
```

or 

```toml
[env]
OPENAI_BASE_URL = "<url>"
OPENAI_API_KEY = "<key>"
```

If you're using a different provider, you can add the variables needed by hand.

These env vars can be overridden with values from the environment, e.g.:

```bash
OPENROUTER_API_KEY=<other-key> faberon serve
```

## Optional deployment knobs

- `proposer_timeout`: timeout (in seconds) for one proposer LLM call (default 600).
- `state_dir`: the local executor's private state directory (default `~/.local/share/faberon`). Holds one pid record per job for restart recovery.
- `max_time`: walltime cap in minutes; can only lower a plan's walltime, never raise it. Absent means no cap.
