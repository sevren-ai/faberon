## Faberon environment

First, generate a unique `<token>` that will secure the API on a shared host:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

then use this token:

```bash
export FABERON_API_TOKEN=<token>
```

If you're on a login node with access to Slurm, set your slurm account ID:

```bash
export FABERON_SLURM_ACCOUNT=<account>
```

## LLM model

If you're using OpenRouter:

```bash
export OPENROUTER_API_KEY=<key>
export FABERON_MODEL=openrouter:<provider>/<model>
```

For a local model with an OpenAI-compatible API, use the following instead:
```bash
export OPENAI_BASE_URL=<url>
export OPENAI_API_KEY=local
export FABERON_MODEL=openai:<model>
```

## Optional deployment knobs

When you're running Faberon, there are some optional settings you can set through envvars as well:

- `FABERON_EXECUTOR`: which executor runs jobs, `slurm` or `local`. Default is `slurm` when `sbatch` is on `PATH`, otherwise `local`. Set it to override the detection.
- `FABERON_MAX_TIME`: walltime cap in minutes; can only lower a plan's walltime, never raise it.
- `FABERON_PROPOSER_TIMEOUT`: timeout (in seconds) for one proposer LLM call (default 600).
- `FABERON_NO_RECOVER`: serve the API without resuming pending workflows at startup. See [troubleshooting.md](troubleshooting.md#safe-restart-and-recovery).

### Slurm-specific options

- `FABERON_SLURM_GPUS`: GPU count per job (default 1). Only used with the Slurm executor.

### Local-executor-specific options

- `FABERON_STATE_DIR`: the local executor's private state directory (default `~/.local/share/faberon`). Holds one pid record per job for restart recovery.

### Location of the Faberon server

If you change where the server binds, tell the clients where to find it. The server reads its bind address; the clients read its URL:

Server-side (read by `faberon serve`):
- `FABERON_HOST`: address `faberon serve` binds to (default `127.0.0.1`).
- `FABERON_PORT`: port `faberon serve` binds to (default `8000`).

Client-side (read by the `faberon` CLI and Faberon Chat):
- `FABERON_API_URL`: where clients reach the running Faberon server (default `http://127.0.0.1:8000`). Must match `FABERON_HOST:FABERON_PORT` if you changed those.