# Faberon: Roadmap

**Status:** living document. Features planned for the near future, plus open questions that affect that work. Updated whenever plans or decisions change, by humans or by agents (see `AGENTS.md`). Stable architecture lives in [design.md](design.md). Speculative ideas and deferred options live in [future.md](future.md). This doc is not a history: git records what shipped and why.

**Current focus:** v0.2.0 (autonomy). Scope and progress: [v0.2.0.md](v0.2.0.md).

## Phases

A version is a milestone release, not the whole roadmap. Each phase becomes its own version with its own design doc when its design review happens.

- **v0.2.0: autonomy.** The campaign-level loop: propose → run → judge → keep/discard → repeat, bounded by a max-experiments cap and budget. Pydantic AI proposer (typed tools: read ledger, read `train.py`, propose edit, commit), git-commit lineage with sequential checkouts (`max_concurrency=1`, so no worktrees yet), plan stop conditions honored (hard caps first, LLM-parsed phrasing as a stand-in). Pulled forward from v0.3.0 because autonomy needs them: `--time` walltime on sbatch and a cancel path (cancel signal checked at every loop decision boundary). Continues testing against autoresearch.
- **v0.3.0: console.** Pi extension on the login node: drafter intake, `inject_idea`, `runs_status`, `approve`, live SSE widget (runs, budget burn, pending approvals).
- **v0.4.0: scale.** Concurrency-limited queue for ablations (git worktrees arrive here, one linked working tree per job on its own commit, shared venv and data); real budget enforcement if not already covered by the gate work; epilog webhook once egress is verified; restart drills as routine.
- **v0.5.0: research quality.** Judgment quality (robust confidence measure, eval-suite non-regression backpressure, constraint-aware gates); living notes file; plan stop-conditions honored end-to-end (LLM-parsed, not stand-in). The ledger records parent and new sha so the lineage tree is reconstructable.

## Open Questions

Questions that affect near-term work. Broader deferred ideas belong in [future.md](future.md).

- Compute-node to login-node HTTP egress (gates the epilog webhook).
- LLM access from the login node for the v0.2.0 proposer (and later the drafter): hosted API egress vs local model, provider choice, key handling (`FABERON_MODEL` env config is already the design.md choice; the operational path is not).
- Cluster specifics: partition, GPU type, and QoS are not currently set by the executor. Explicit `--partition` and QoS belong with the scale work (v0.4.0); `--time` walltime is pulled forward to v0.2.0.
- Constraint-aware judgment: today judgment scores one metric movement with a confidence measure. Constraint-driven search (e.g. edge models that must fit a size or memory budget) needs a hard gate distinct from the scored objective: keep only if the metric moves AND the run satisfies a budget. Settles where the constraint lives (plan schema field vs. judgment step) and whether it is a per-run gate or a campaign-level rule.
- Frontier exploration: keeping several branch tips alive per campaign instead of one best (idea described in future.md). Settles at the v0.4.0 design review, where worktrees arrive: the pruning rule (when a branch dies: dominated, budget share, age), how the proposer chooses which branch to extend (exploit the leader vs explore the rest), and what `campaign.ended` reports when several branches survive.
