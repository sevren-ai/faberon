# Contributing to Faberon

Process rules for every contributor, human or agent.

## Bugs and feature requests

We are not accepting pull requests for new features right now. Please do not open a feature PR.

- **Bug reports:** file an issue at [github.com/sevren-ai/faberon/issues](https://github.com/sevren-ai/faberon/issues).
- **Feature requests:** post in the [feature-requests discussion](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests), not as an issue or PR.

## Code Layout

- `packages/brain/`: the brain (Python, `uv`-managed, import name `faberon`)
- `packages/chat/`: Faberon Chat (Pi extension, TypeScript, npm-managed)
- `docs/design/`: [system design](docs/design/design.md), [roadmap](docs/design/roadmap.md), [future ideas](docs/design/future.md), one doc per release (shipped releases in [archive/](docs/design/archive/))
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) (this document): process rules for every contributor, human or agent
- [`AGENTS.md`](../AGENTS.md): agent-specific rules, read first by any coding agent

## Planned work and roadmap

Faberon's stable system design is documented in `docs/design/design.md`. All work should adhere to it. 
Features planned for the near future are recorded in `docs/design/roadmap.md` and more specific releases are planned in `docs/design/vX.Y.Z.md` files.

To suggest a new high-level idea or feature, these design docs can be edited and PR'd by maintainers of the code base. 
This is the perfect point in time to discuss high-level design decisions. They shouldn't be edited by external contributors - they can open a discussion thread instead.

Follow-up code PRs should largely follow those design docs, though small deviations may be warranted. 
In those cases, the PRs should edit the design docs to keep them in-sync and to alert other maintainers of the design choices that were made.

The current WIP release(s) usually contain a progress TODO list. Check off items in the same PR that implements the work.

Never use code comments to document speculative ideas or TODO items.

Smaller TODO items can be logged as issues on the Github tracker, feature requests by external contributors should be logged in the relevant [discussion forum](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests).
Issues and discussions that are adopted into the design docs, may be closed as they are then considered to be work-in-progress.

### Releases and versioning

The two packages version independently; the design makes them independently replaceable. What keeps them compatible is the API contract version (`v0` today), not a shared release number. The tag names are asymmetric on purpose:

- **Brain** (`packages/brain/`, the default artifact): tag `vX.Y.Z`, for example `v0.2.2`. Bare, no prefix, matching the tags that already exist. (cf. `packages/brain/pyproject.toml` and `faberon.__version__`)
- **Faberon Chat** (`packages/chat/`): tag `chat-vX.Y.Z`, first release `chat-v0.1.0`. Prefixed so chat tags never collide with brain tags. (cf. `packages/chat/package.json`)

Cut a release by bumping the version and pushing the package's tag:

```bash
# brain
git tag v0.3.0 && git push origin v0.3.0

# chat
git tag chat-v0.1.0 && git push origin chat-v0.1.0
```

GitHub Releases keys off the tag you push; each release notes which contract version it speaks. Both packages are also published to their registries: the brain to PyPI as `faberon` (`uv publish`, built from a worktree at the tag, never from a feature branch) and the chat interface to npm as `@faberon/chat` (`npm publish --access public`).

After a release, the related `vX.Y.Z.md` (if it exists) is archived and becomes frozen.

## Git and pull requests

- Work on feature branches. Keep PRs small and self-contained.
- Agents must not commit, push, or open PRs. A human reviews the changes, commits, pushes, and opens the PR.
- Humans write the PR description themselves: concise, readable, no long LLM-generated walls of text. Agents must not draft the description, not even in chat. Follow the PR template in `.github/PULL_REQUEST_TEMPLATE.md` (summary, AI disclaimer, reviewer guidelines, and the on-cluster integration test output).
- `main` stays green. CI runs `ruff`, `ty`, and the test suite (`.github/workflows/lint.yml`, `.github/workflows/test.yml`) on every PR and on `main`; a red run blocks the merge.
- A release is cut by merging to `main` and pushing the package's tag.

### PR reviewing

For a contributor opening a PR:
- Allows follow the PR template. Declare AI usage and the output for the integration tests run on Slurm, when relevant.

For any reviewer:
- When providing comments, for clarity you can mark them with one of the following prefixes:
  - blocking (important comments that should be resolved before merging)
  - nit (smaller things that should be addressed or discussed before merging)
  - optional (smaller things that are optional to address and don't influence approval status)
  - discussion (a question or comment to follow-up on, not necessarily requiring a code change)
  - kudos (name the good things in the PR specifically)

## Testing

### Local tests (workspace)

From the repo root:

```bash
bash scripts/test/local.sh
```

This runs `uv sync --locked` and `uv run pytest` in `packages/brain/`, mirroring `.github/workflows/test.yml`.

- Test functional behaviour through the public API of the unit under test. Do not assert on internals that a refactor could change without changing behaviour.
- Keep tests small and focused. One behaviour per test when practical.
- Roughly one test file per Python module, mirroring the package layout (for example `schema/plan.py` → `tests/test_schema/test_plan.py`).
- Every test should protect a behaviour we care about. Prefer a few meaningful tests over many trivial ones that only restate the implementation.
- Tests that start DBOS workflows must wait for them to finish before DBOS teardown. A running parent can otherwise remain blocked on a child workflow during Python shutdown.

#### Postgres ledger tests

They are included in the local tests, but skip themselves when Postgres is unreachable. The suite takes the database URL from your Faberon config file, redirects it to the `faberon_test` database, and recreates that database from scratch on every run. The tests truncate tables and reset the DBOS system database, so this separation keeps production data safe.


### Slurm tests (login node)

```bash
bash scripts/test/slurm.sh
```

This (only) runs the tests that submit real jobs to Slurm. It requires `sbatch` on `PATH` and `slurm_account` in the Faberon config file.

To run them on a login node that has `sbatch` on `PATH`:

### LLM tests

```bash
bash scripts/test/llm.sh
```

This runs the proposer against the real model configured as `model` in the Faberon config file.

### LLM + Slurm tests (login node)

```bash
bash scripts/test/prod.sh
```

Run the Slurm and LLM integration tests together.

### Chat tests

```bash
npm ci --legacy-peer-deps   # npm 10's peer resolver mis-handles Pi's tree
npx tsc --noEmit            # typecheck
npx vitest run              # tests
```


## Formatting and linting

Ruff formats and lints the Python code. From the repo root:

```bash
bash scripts/lint.sh
```

This runs `uv sync --locked`, `ruff format`, `ruff check --fix`, and `ty check` in `packages/brain/`. It writes formatting and lint fixes back to the source. CI (`.github/workflows/lint.yml`) runs the check-only variants (`ruff format --check`, `ruff check`, `ty check`) and blocks the merge on a red run. Run `scripts/lint.sh` before pushing.

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
