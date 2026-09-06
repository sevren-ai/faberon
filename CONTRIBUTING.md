# Contributing to Faberon

Process rules for every contributor, human or agent.

## What to work on

Read the design docs before starting, in this order:

1. `docs/design/design.md`: the stable system design.
2. `docs/design/roadmap.md`: features planned for the near future, plus open questions.
3. The current WIP release doc: the `docs/design/vX.Y.Z.md` whose status line reads "current WIP".

How to use them:

- Work targets the current WIP release. Its progress checklist is the to-do list.
- Check off items in the same commit/PR that implements the work.
- Update docs in the same commit/PR that changes a decision: `roadmap.md` for plan changes, `design.md` only when the stable architecture genuinely changes.
- Speculative ideas belong in `docs/design/future.md`, not in the roadmap or in code comments.
- The current WIP release doc stays editable until it ships. Never edit a `vX.Y.Z.md` after that version has shipped.
- When starting work toward a new release, bump the version at the start of the feature branch (`packages/control-plane/pyproject.toml` and `faberon.__version__`), so every artifact knows what it is working toward. Do not wait until merge time.

## Git and pull requests

- Work on feature branches. Keep PRs small and self-contained.
- Agents must not commit, push, or open PRs. A human reviews the changes, commits, pushes, and opens the PR.
- Humans write the PR description themselves: concise, readable, no long LLM-generated walls of text. Follow the PR template in `.github/PULL_REQUEST_TEMPLATE.md` (summary, AI disclaimer, and the on-cluster Slurm integration test output).
- `main` stays green. CI runs `ruff`, `ty`, and the test suite (`.github/workflows/lint.yml`, `.github/workflows/test.yml`) on every PR and on `main`; a red run blocks the merge.
- A release is cut by merging to `main` and tagging `vX.Y.Z`.

## Testing

From the repo root:

```bash
scripts/test.sh
```

This runs `uv sync --locked` and `uv run pytest` in `packages/control-plane/`, mirroring `.github/workflows/test.yml`.

- Test functional behaviour through the public API of the unit under test. Do not assert on internals that a refactor could change without changing behaviour.
- Keep tests small and focused. One behaviour per test when practical.
- Roughly one test file per Python module, mirroring the package layout (for example `schema/plan.py` → `tests/test_schema/test_plan.py`).
- Every test should protect a behaviour we care about. Prefer a few meaningful tests over many trivial ones that only restate the implementation.

### Ledger tests

The ledger tests need a local Postgres and `FABERON_DATABASE_URL` exported in your shell (see `## Prerequisites` and the `## Setup` section of `README.md`). They skip themselves when `FABERON_DATABASE_URL` is unset, so a plain `scripts/test.sh` run doesn't need a database.

### On-cluster Slurm tests

Tests that submit real jobs to Slurm live in `tests/test_executor/test_slurm_integration.py`. They are skipped by default so a plain `pytest` run never submits jobs, in CI or on a login node. To run them on a login node that has `sbatch` on `PATH`:

```bash
FABERON_SLURM_ACCOUNT=<account> scripts/test_slurm.sh
```

`FABERON_SLURM_ACCOUNT` is the Slurm account jobs are billed to; the cluster requires it. The script sets `FABERON_SLURM_INTEGRATION=1` to opt in and runs `pytest -m slurm`. These verify actual behaviour on the cluster.

## Formatting and linting

Ruff formats and lints the Python code. From the repo root:

```bash
scripts/lint.sh
```

This runs `uv sync --locked`, `ruff format`, `ruff check --fix`, and `ty check` in `packages/control-plane/`. It writes formatting and lint fixes back to the source. CI (`.github/workflows/lint.yml`) runs the check-only variants (`ruff format --check`, `ruff check`, `ty check`) and blocks the merge on a red run. Run `scripts/lint.sh` before pushing.

## Coding style

- Prefer the simplest implementation that works. Do not add optional fields, defaults, or forward-looking abstractions until the current feature needs them.
- Production code is written for production, not for the tests. Keep test accommodations out of the main package:
  - Do not add parameters, constructors, or protocols whose primary purpose is to let a test substitute a fake.
  - Do not add test-only defaults, flags, or branches that exist solely so a test can reach in.
- Optional parameters (those with defaults) are typically keyword-only, separated from required parameters by `*` in the function declaration. 

### Imports

Use relative imports inside a package (`from .events import Event`), not absolute (`from faberon.schema.events import Event`). This keeps packages relocatable and signals the sibling relationship at the call site.

Absolute imports are for cross-package boundaries (`from faberon.executor import Executor`). The test suite is itself a package: use relative imports within it, absolute imports to reach `faberon`.


## GitHub Actions

- Pin actions to full-length commit SHAs with a version comment (for example `actions/checkout@3d3c42e5... # v7.0.1`), never to moving tags.

## Writing style

- Docs in this repo are written plainly: short sentences, no em-dashes, no hype. Agents follow the detailed style guide in `AGENTS.md`; human-written prose follows the same spirit.
