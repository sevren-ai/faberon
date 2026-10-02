# Contributing to Faberon

Process rules for every contributor, human or agent.

## Bugs and feature requests

We are not accepting pull requests for new features right now. Please do not open a feature PR.

- **Bug reports:** file an issue at [github.com/sevren-ai/faberon/issues](https://github.com/sevren-ai/faberon/issues).
- **Feature requests:** post in the [feature-requests discussion](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests), not as an issue or PR.

## What is work in progress

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
- Bump the version right before a release is cut: `packages/control-plane/pyproject.toml` and `faberon.__version__` for the control plane, `packages/console/package.json` for the console.

### Releases and versioning

The two packages version independently; the design makes them independently replaceable. What keeps them compatible is the API contract version (`v0` today), not a shared release number. The tag names are asymmetric on purpose:

- **Control plane** (`packages/control-plane/`, the default artifact): tag `vX.Y.Z`, for example `v0.2.2`. Bare, no prefix, matching the tags that already exist.
- **Console** (`packages/console/`): tag `console-vX.Y.Z`, first release `console-v0.1.0`. Prefixed so console tags never collide with control-plane tags.

Cut a release by merging to `main`, bumping that package's version, and pushing the package's tag:

```bash
# control plane
git tag v0.3.0 && git push origin v0.3.0

# console
git tag console-v0.1.0 && git push origin console-v0.1.0
```

GitHub Releases keys off the tag you push; each release notes which contract version it speaks. Both packages are also published to their registries: the brain to PyPI as `faberon` (`uv publish`, built from a worktree at the tag, never from a feature branch) and the console to npm as `@faberon/console` (`npm publish --access public`). Until the first registry publish lands (see the v0.3.0 design doc), the console installs from the repo with `pi install git:github.com/sevren-ai/faberon@console-v0.1.0`.

For environment setup to develop Faberon (both packages, the test and lint scripts), see [docs/developing.md](docs/developing.md).

## Git and pull requests

- Work on feature branches. Keep PRs small and self-contained.
- Agents must not commit, push, or open PRs. A human reviews the changes, commits, pushes, and opens the PR.
- Humans write the PR description themselves: concise, readable, no long LLM-generated walls of text. Agents must not draft the description, not even in chat. Follow the PR template in `.github/PULL_REQUEST_TEMPLATE.md` (summary, AI disclaimer, and the on-cluster integration test output).
- `main` stays green. CI runs `ruff`, `ty`, and the test suite (`.github/workflows/lint.yml`, `.github/workflows/test.yml`) on every PR and on `main`; a red run blocks the merge.
- A release is cut by merging to `main` and pushing the package's tag.

## Testing

From the repo root:

```bash
bash scripts/test/local.sh
```

This runs `uv sync --locked` and `uv run pytest` in `packages/control-plane/`, mirroring `.github/workflows/test.yml`.

- Test functional behaviour through the public API of the unit under test. Do not assert on internals that a refactor could change without changing behaviour.
- Keep tests small and focused. One behaviour per test when practical.
- Roughly one test file per Python module, mirroring the package layout (for example `schema/plan.py` → `tests/test_schema/test_plan.py`).
- Every test should protect a behaviour we care about. Prefer a few meaningful tests over many trivial ones that only restate the implementation.
- Tests that start DBOS workflows must wait for them to finish before DBOS teardown. A running parent can otherwise remain blocked on a child workflow during Python shutdown.

### Ledger tests

The ledger tests need a local Postgres and `FABERON_DATABASE_URL` exported in your shell (see `## Prerequisites` and the `## Setup` section of `README.md`). They skip themselves when `FABERON_DATABASE_URL` is unset or when the postgres isn't running,
so a plain `scripts/test/local.sh` run doesn't need a database.

The test suite runs against the `faberon_test` database, not the actual (production) database named in `FABERON_DATABASE_URL`. The tests truncate tables and reset the DBOS system database, so this separation keeps production data safe. `scripts/db/create-faberon-db.sh` creates both databases.

### On-cluster Slurm tests

Tests that submit real jobs to Slurm live in `tests/test_executor/test_slurm_integration.py`. They are skipped by default so a plain `pytest` run never submits jobs, in CI or on a login node. To run them on a login node that has `sbatch` on `PATH`:

```bash
FABERON_SLURM_ACCOUNT=<account> bash scripts/test/slurm.sh
```

`FABERON_SLURM_ACCOUNT` is the Slurm account jobs are billed to; the cluster requires it. The script sets `FABERON_SLURM_INTEGRATION=1` to opt in and runs `pytest -m slurm`. These verify actual behaviour on the cluster.

### LLM tests

`tests/test_workflow/test_proposer_llm.py` runs the proposer against the real model configured in `FABERON_MODEL`. It is skipped by default. To run it:

```bash
FABERON_MODEL=openrouter:<provider>/<model> OPENROUTER_API_KEY=<key> bash scripts/test/llm.sh
```

Use `scripts/test/prod.sh` to run the Slurm and LLM integration tests together; it needs both sets of env vars.

## Formatting and linting

Ruff formats and lints the Python code. From the repo root:

```bash
bash scripts/lint.sh
```

This runs `uv sync --locked`, `ruff format`, `ruff check --fix`, and `ty check` in `packages/control-plane/`. It writes formatting and lint fixes back to the source. CI (`.github/workflows/lint.yml`) runs the check-only variants (`ruff format --check`, `ruff check`, `ty check`) and blocks the merge on a red run. Run `scripts/lint.sh` before pushing.

## Coding style

- Prefer the simplest implementation that works. Do not add optional fields, defaults, or forward-looking abstractions until the current feature needs them.
- Docstrings are succinct. One short paragraph that says what the unit is and, when useful, why. Do not narrate mechanics, and do not duplicate what design docs, tests, or the type signature already say elsewhere.
- Production code is written for production, not for the tests. Keep test accommodations out of the main package:
  - Do not add parameters, constructors, or protocols whose primary purpose is to let a test substitute a fake.
  - Do not add test-only defaults, flags, or branches that exist solely so a test can reach in.
- Optional parameters (those with defaults) are typically keyword-only, separated from required parameters by `*` in the function declaration.
- Do not use `from __future__ import annotations`. The project requires Python 3.14, so modern annotation syntax (`X | Y`, `list[str]`, etc.) works natively at runtime. Write annotations directly.

### Imports

Use relative imports inside a package (`from .events import Event`), not absolute (`from faberon.schema.events import Event`). This keeps packages relocatable and signals the sibling relationship at the call site.

Absolute imports are for cross-package boundaries (`from faberon.executor import Executor`). The test suite is itself a package: use relative imports within it, absolute imports to reach `faberon`.

### Package layout

Where things go:

- `faberon/schema/`: contract shapes that cross a process boundary: the research plan, events. 
- `faberon/workflow/`: durable workflows (runtime, campaign). `models.py` holds internal data shapes passed between workflow modules: `ExperimentSetup`, `ExperimentResult`, `CampaignSetup`.
- `faberon/executor/`: the executor protocol and its implementations.
- `faberon/ledger/`: the append-only event ledger.
- `faberon/api/`: FastAPI routes. Validation and orchestration only, no business logic.

Placement rules:

- Client-facing shapes live in `schema/`; workflow-internal shapes live in `workflow/models.py`.
- Group a model with its siblings, not inside the module that happens to produce it.


## GitHub Actions

- Pin actions to full-length commit SHAs with a version comment (for example `actions/checkout@3d3c42e5... # v7.0.1`), never to moving tags.

## Writing style

- Docs in this repo are written plainly: short sentences, no em-dashes, no hype. Agents follow the detailed style guide in `AGENTS.md`; human-written prose follows the same spirit.
