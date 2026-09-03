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
- Humans write the PR description themselves: concise, readable, no long LLM-generated walls of text. Explain briefly what the PR does and why. If an agent helped with the implementation, disclose that under an `## AI Disclaimer` subheader in the PR body.
- `main` stays green. CI runs `ruff`, `ty`, and the test suite (`.github/workflows/lint.yml`, `.github/workflows/test.yml`) on every PR and on `main`; a red run blocks the merge.
- A release is cut by merging to `main` and tagging `vX.Y.Z`.

## Testing

From the repo root:

```bash
scripts/test.sh
```

This runs `uv sync --locked` and `uv run pytest` in `packages/control-plane/`, mirroring `.github/workflows/test.yml`.

## Formatting and linting

Ruff formats and lints the Python code. From the repo root:

```bash
scripts/lint.sh
```

This runs `uv sync --locked`, `ruff format --check`, `ruff check`, and `ty check` in `packages/control-plane/`, mirroring `.github/workflows/lint.yml`. To apply formatting and lint fixes instead of just checking:

```bash
cd packages/control-plane
uv run ruff format src tests
uv run ruff check --fix src tests
```

CI runs `ruff format --check`, `ruff check`, and `ty check` on every PR. A red run blocks the merge. Run `scripts/lint.sh` before pushing.

- Test functional behaviour through the public API of the unit under test. Do not assert on internals that a refactor could change without changing behaviour.
- Keep tests small and focused. One behaviour per test when practical.
- Roughly one test file per Python module, mirroring the package layout (for example `schema/plan.py` → `tests/test_schema/test_plan.py`).
- Every test should protect a behaviour we care about. Prefer a few meaningful tests over many trivial ones that only restate the implementation.

## GitHub Actions

- Pin actions to full-length commit SHAs with a version comment (for example `actions/checkout@3d3c42e5... # v7.0.1`), never to moving tags.

## Writing style

- Docs in this repo are written plainly: short sentences, no em-dashes, no hype. Agents follow the detailed style guide in `AGENTS.md`; human-written prose follows the same spirit.
