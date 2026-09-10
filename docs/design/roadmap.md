# Faberon: Roadmap

**Status:** living document. Features planned for the near future, plus open questions that affect that work. Updated whenever plans or decisions change, by humans or by agents (see `AGENTS.md`). Stable architecture lives in [design.md](design.md). Speculative ideas and deferred options live in [future.md](future.md). This doc is not a history: git records what shipped and why.

**Current focus:** v0.2.0

## Phases

A version is a milestone release, not the whole roadmap. Each phase becomes its own version with its own design doc when its design review happens.

- **v0.2.0** Pi extension on the login node: drafter intake, `inject_idea`, `runs_status`, `approve`, live SSE widget (runs, budget burn, pending approvals).
- **v0.3.0: scale and safety** Concurrency-limited queue for ablations; budget caps and approval gates; epilog webhook once egress is verified; restart drills as routine.
- **v0.4.0: research policy** The full propose → run → judge → keep/discard loop with agent-authored `train.py` edits; living notes file; plan stop-conditions honored end-to-end. Lineage is git commits: each edit is a commit, keep promotes it to the lineage head, discard reverts to the parent, branch forks from a kept commit. The ledger records parent and new sha so the tree is reconstructable. Parallel experiments (concurrency > 1) use `git worktree` (one linked working tree per job on its own commit, sharing the object store), with a shared venv and data so worktrees don't re-setup.

## Open Questions

Questions that affect near-term work. Broader deferred ideas belong in [future.md](future.md).

- Compute-node to login-node HTTP egress (gates the Phase 3 epilog webhook).
- Cluster specifics for Phase 3: partition, GPU type, QoS, and walltime limits are not currently set by the executor. Phase 3 needs explicit `--time`, `--partition`, and QoS for safety against runaway jobs.
- Constraint-aware judgment: today judgment scores one metric movement with a confidence measure. Constraint-driven search (e.g. edge models that must fit a size or memory budget) needs a hard gate distinct from the scored objective: keep only if the metric moves AND the run satisfies a budget. Settles where the constraint lives (plan schema field vs. judgment step) and whether it is a per-run gate or a campaign-level rule.
