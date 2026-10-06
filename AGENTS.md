# AGENTS.md

You are a contributor: follow [CONTRIBUTING.md](CONTRIBUTING.md) for process (what to work on, git/PRs, testing, CI). This file adds what is specific to working as an agent.

## Context loading

Before any contribution, load context in this order:

1. `docs/design/design.md`: the stable system design.
2. `docs/design/roadmap.md`: planned features and open questions.
3. The current WIP release doc: the `docs/design/vX.Y.Z.md` whose status line reads "current WIP".

## Boundaries

- Treat sandbox and permission limits as hard stops. When a command is blocked, report the blocker and wait. Never route around them (no `su`, no alternate paths, no side steps).
- Do not install infrastructure (databases, services, system packages). If a test needs an external service, stop and ask the user to start it.

## Writing style

Applies to everything you produce: design docs, READMEs, code comments, commit messages, and chat replies.

- Never use em-dashes (—) or en-dashes (–) as punctuation. Use a colon, a period, a comma, or parentheses instead. Hyphens in compound words (keep/discard) are fine.
- Keep sentences short and declarative. One idea per sentence.
- Avoid typical LLM-generated phrasing:
  - Filler openers: "It's worth noting", "Moreover", "Furthermore", "Interestingly".
  - Dramatic contrasts: "not X, but Y".
  - Hype words: "seamless", "powerful", "cutting-edge".
  - Sentences that restate the heading or the previous sentence.
- Banned words: "seam" and "load-bearing". Say "contract" or "boundary" instead of "seam", and "critical" or "essential" instead of "load-bearing".
- Prefer concrete statements over abstract framing.
- Code comments and docstrings document what is there and, when useful, why. Do not use them to plan future work; that belongs in the design docs.

Examples:

Bad: "The brain — the only component that decides — seamlessly orchestrates experiments."
Good: "The brain is the only component that decides. It runs the experiments."

Bad: "Moreover, it's worth noting that the ledger is append-only."
Good: "The ledger is append-only."
