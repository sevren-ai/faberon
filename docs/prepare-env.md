## Faberon environment

By default, `FABERON_API_URL` will be set to `http://127.0.0.1:8000`, but if you want to serve the brain elsewhere you can set this envvar.

Next, generate a unique `<token>` that will secure the API on a shared host:
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

- `FABERON_HOST`: address `faberon serve` binds to (default `127.0.0.1`).
- `FABERON_PORT`: port `faberon serve` binds to (default `8000`).
- `FABERON_SLURM_GPUS`: GPU count per job (default 1).
- `FABERON_SLURM_MAX_TIME`: walltime cap in minutes; can only lower a plan's walltime, never raise it.
- `FABERON_SLURM_OUTPUT`: Slurm `--output` path for job stdout/stderr.
- `FABERON_PROPOSER_TIMEOUT`: timeout (in seconds) for one proposer LLM call (default 600).
- `FABERON_NO_RECOVER`: serve the API without resuming pending workflows at startup. See [troubleshooting.md](troubleshooting.md#safe-restart-and-recovery).