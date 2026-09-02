# Contributing to Faberon

Process rules for every contributor, human or agent.

## Before you start

Read the design docs:

1. `docs/design/design.md`: the stable system design.
2. `docs/design/roadmap.md`: features planned for the near future, plus open questions.
3. The current WIP release doc: the `docs/design/vX.Y.Z.md` whose status line reads "current WIP".

## Repository workflow

- Work happens on feature branches merged by PR. Keep PRs small and self-contained.
- Work targets the current WIP release. When starting work toward a new release, bump the version at the start of the feature branch (`packages/control-plane/pyproject.toml` and `faberon.__version__`), so every artifact knows what it is working toward. Do not wait until merge time.
- A release is cut by merging to `main` and tagging `vX.Y.Z`.
- `main` stays green. CI (`.github/workflows/test.yml`) runs the test suite on every PR and on `main`; a red run blocks the merge.

## Keeping docs in sync

- When a change makes a new decision or changes an existing one, update the docs in the same PR: `docs/design/roadmap.md` for plan changes, `docs/design/design.md` only when the stable architecture genuinely changes.
- The current WIP release doc stays editable until it ships.
- Never edit `docs/design/vX.Y.Z.md` for a version that has already shipped (a git tag with that version exists). 

## GitHub Actions

- Pin actions to full-length commit SHAs with a version comment (for example `actions/checkout@3d3c42e5... # v7.0.1`), never to moving tags.

## Writing style

- Docs in this repo are written plainly: short sentences, no em-dashes, no hype. Agents follow the detailed style guide in `AGENTS.md`; human-written prose follows the same spirit.
- PR descriptions should be concise and readable, no long LLM-generated walls of text. Explain briefly what the PR does and why.
