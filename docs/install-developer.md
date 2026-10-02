# Developing Faberon

Set up a development checkout to work on Faberon itself. Process rules (branches, PRs, CI, style) live in [CONTRIBUTING.md](../CONTRIBUTING.md); this doc is the environment setup. Users who only want to *run* Faberon install it instead: [install-workstation.md](install-workstation.md) or [install-login-node.md](install-login-node.md).

## Get the repo

Development needs a real clone, unlike the user install paths:

```bash
git clone https://github.com/sevren-ai/faberon
cd faberon
```

On a login node, the dev loop is: work on a workstation, push to GitHub, pull on the login node.

## Layout

- `packages/control-plane/`: the brain (Python, `uv`-managed, import name `faberon`); being renamed to `packages/brain/`
- `packages/console/`: the console (Pi extension, TypeScript, npm-managed)
- `docs/design/`: [system design](design/design.md), [roadmap](design/roadmap.md), [future ideas](design/future.md), one doc per release (shipped releases in [archive/](design/archive/))
- [`CONTRIBUTING.md`](../CONTRIBUTING.md): process rules for every contributor, human or agent
- [`AGENTS.md`](../AGENTS.md): agent-specific rules, read first by any coding agent

## The brain (Python)

Requires Python 3.14 and `uv`. From the repo root:

```bash
bash scripts/test/local.sh   # uv sync --locked, then pytest (and the console tests)
bash scripts/lint.sh         # ruff format/check, ty, then the console checks
```

These mirror CI and run both the brain and the console suites. The brain package is `packages/control-plane` (being renamed to `packages/brain/`; see the v0.3.0 design doc).

Some tests need services and are skipped by default:

- **Postgres tests** need `FABERON_DATABASE_URL` set and a local Postgres running (see the install guides for setup). They run against the `faberon_test` database.
- **Slurm tests** (`bash scripts/test/slurm.sh`) need `sbatch` on `PATH` and `FABERON_SLURM_ACCOUNT`.
- **LLM tests** (`bash scripts/test/llm.sh`) need `FABERON_MODEL` and the provider key.

## The console (TypeScript)

Requires Node 22.19 or newer. On a workstation, install it through your package manager; on a login node, install it user-space (see [install-login-node.md](install-login-node.md#4-the-console-optional)). From `packages/console/`:

```bash
npm ci --legacy-peer-deps   # npm 10's peer resolver mis-handles Pi's tree
npx tsc --noEmit            # typecheck
npx vitest run              # tests
```

To try the extension against a running brain, load it from source (no build step; Pi compiles the TypeScript at load). The `pi` binary is installed locally by `npm ci`, not on your `PATH`, so invoke it through `npx` from `packages/console/`:

```bash
export FABERON_API_TOKEN=<token>
export OPENROUTER_API_KEY=<key>   # pi's own LLM provider
npx pi -e src/index.ts
```

Two separate credentials are in play. `FABERON_API_TOKEN` is the bearer token the console sends to authenticate against the brain; it must match the token the brain was started with (generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and pass it to both `faberon serve` and the console; see [install-workstation.md](install-workstation.md)). Independently, **pi is an AI agent and needs its own LLM provider to run at all**: without one it exits with "No API key found for the selected model." Set a provider key (for example `OPENROUTER_API_KEY`, or `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and so on) before launching, or run `/login` inside pi for an OAuth flow. The full provider list is in `packages/console/node_modules/@earendil-works/pi-coding-agent/docs/providers.md`. `FABERON_API_URL` defaults to `http://127.0.0.1:8000`; set it only if the brain is elsewhere.

(Alternatively, install Pi globally with `npm install -g @earendil-works/pi-coding-agent` so `pi` is on your `PATH`, as the install guides do for end users. Then plain `pi -e packages/console/src/index.ts` works from the repo root.)

This adds the `faberon_list_campaigns` tool and a `/faberon-list` command. Write operations, live status, and the drafter build on this layer; see [design/v0.3.0.md](design/v0.3.0.md).

## Design docs

- Stable architecture is [design/design.md](design/design.md)
- Near-term plans are [design/roadmap.md](design/roadmap.md)
- Each release has a `design/vX.Y.Z.md`

Read them before contributing; the order is in [AGENTS.md](../AGENTS.md).
