# AGENTS.md

Guidance for any coding agent working in this repository.

## Writing style

Applies to all prose the agent produces: design docs, READMEs, code comments, commit messages, and chat replies.

- Never use em-dashes (—) or en-dashes (–) as punctuation. Use a colon, a period, a comma, or parentheses instead. Hyphens in compound words (control-plane, keep/discard) are fine.
- Keep sentences short and declarative. One idea per sentence.
- Avoid typical LLM-generated phrasing:
  - Filler openers: "It's worth noting", "Moreover", "Furthermore", "Interestingly".
  - Dramatic contrasts: "not X, but Y".
  - Hype words: "seamless", "powerful", "cutting-edge".
  - Sentences that restate the heading or the previous sentence.
- Banned words: "seam" and "load-bearing". Say "contract" or "boundary" instead of "seam", and "critical" or "essential" instead of "load-bearing".
- Prefer concrete statements over abstract framing.

Examples:

Bad: "The control plane — the only component that decides — seamlessly orchestrates experiments."
Good: "The control plane is the only component that decides. It runs the experiments."

Bad: "Moreover, it's worth noting that the ledger is append-only."
Good: "The ledger is append-only."

## Repository workflow

Before any contribution, load context in this order:

1. `docs/design/design.md`: the stable system design.
2. `docs/design/roadmap.md`: planned work, open questions, and the decision log.
3. The current WIP release doc: the `docs/design/vX.Y.Z.md` whose status line reads "current WIP". `roadmap.md` names the current focus.

Rules:

- Work targets the current WIP release. When starting work toward a new release, bump the version at the start of the feature branch (`packages/control-plane/pyproject.toml` and `faberon.__version__`), so every artifact knows what it is working toward. Do not wait until merge time.
- The default branch is `main`, always. Never `master`.
- A release is cut by merging to `main` and tagging `vX.Y.Z`.
- When a change makes a new decision or changes an existing one, update the docs in the same PR: `roadmap.md` for plan changes, `design.md` only when the stable architecture genuinely changes.
- Never edit `docs/design/vX.Y.Z.md` for a version that has already shipped (a git tag with that version exists). The current WIP release doc stays editable until it ships.
- Keep PRs small and self-contained. `main` stays green.
