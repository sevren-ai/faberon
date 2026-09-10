# Faberon: Roadmap

**Status:** living document. Features planned for the near future, plus open questions that affect that work. Updated whenever plans or decisions change, by humans or by agents (see `AGENTS.md`). Stable architecture lives in [design.md](design.md). Speculative ideas and deferred options live in [future.md](future.md). This doc is not a history: git records what shipped and why.

**Current focus:** v0.1.0, the skeleton. Scope and progress: [v0.1.0.md](v0.1.0.md).

## Phases

A version is a milestone release, not the whole roadmap. Each phase becomes its own version with its own design doc when its design review happens.

- **Phase 0: scaffold.** `uv` monorepo (console package joins as sibling in Phase 2); quarantined schema module; Postgres setup scripts for dev machine and login node.
- **Phase 1: skeleton.** One thin path through every tier. Ships as **v0.1.0**.
- **Phase 2: console v0.1 (planned v0.2.0).** Pi extension on the login node: drafter intake, `inject_idea`, `runs_status`, `approve`, live SSE widget (runs, budget burn, pending approvals).
- **Phase 3: scale and safety (planned v0.3.0).** Concurrency-limited queue for ablations; budget caps and approval gates; epilog webhook once egress is verified; restart drills as routine.
- **Phase 4: research policy (planned v0.4.0).** The full propose → run → judge → keep/discard loop with agent-authored `train.py` edits; living notes file; plan stop-conditions honored end-to-end. Lineage is git commits: each edit is a commit, keep promotes it to the lineage head, discard reverts to the parent, branch forks from a kept commit. The ledger records parent and new sha so the tree is reconstructable. Parallel experiments (concurrency > 1) use `git worktree` (one linked working tree per job on its own commit, sharing the object store), with a shared venv and data so worktrees don't re-setup.

## Open Questions

Questions that affect near-term work. Broader deferred ideas belong in [future.md](future.md).

- Compute-node to login-node HTTP egress (gates the Phase 3 epilog webhook).
- Cluster specifics for v0.1.0: partition, GPU type/count, QoS, walltime limits; login-node internet for data prep.
- Constraint-aware judgment: today judgment scores one metric movement with a confidence measure. Constraint-driven search (e.g. edge models that must fit a size or memory budget) needs a hard gate distinct from the scored objective: keep only if the metric moves AND the run satisfies a budget. Settles where the constraint lives (plan schema field vs. judgment step) and whether it is a per-run gate or a campaign-level rule.
