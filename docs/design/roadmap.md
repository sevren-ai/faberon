# Faberon: Roadmap

**Status:** living document. Features planned for the near future, plus open questions that affect that work. Updated whenever plans or decisions change, by humans or by agents (see `AGENTS.md`). Stable architecture lives in [design.md](design.md). Speculative ideas and deferred options live in [future.md](future.md). This doc is not a history: git records what shipped and why.

**Current focus:** 
* v0.2.1 (robustness): [v0.2.1.md](v0.2.1.md). 
* v0.3.0 (console): [v0.3.0.md](v0.3.0.md).

## Phases

A version is a milestone release, not the whole roadmap. Each phase becomes its own version with its own design doc when its design review happens.

- **v0.3.0: console.** Pi extension on the login node: drafter intake, `inject_idea`, live SSE status (runs, budget burn). Adds an `experiment.proposing` event so the proposer's LLM wait does not read like a hang, and a `faberon` CLI for shell operations. Human-injected ideas are advisory-only for now.
- **v0.4.0: scale.** Concurrency-limited queue for ablations (git worktrees arrive here, one linked working tree per job on its own commit, shared venv and data); real budget enforcement if not already covered by the gate work; epilog webhook once egress is verified; restart drills as routine.
- **v0.5.0: research quality.** Judgment quality (robust confidence measure, eval-suite non-regression backpressure, constraint-aware gates); living notes file; plan stop-conditions honored end-to-end (LLM-parsed, not stand-in). The ledger records parent and new sha so the lineage tree is reconstructable.

## Open Questions

Questions that affect near-term work. Broader deferred ideas belong in [future.md](future.md).

- Database schema versioning: today the schema is created idempotently (`CREATE TABLE IF NOT EXISTS`) and never migrated, so upgrading between versions requires recreating the database and losing its data. Once Faberon has users who cannot do that, adopt a real mechanism: a `schema_version` table, ordered migration steps, a startup check that refuses to run against an unexpected version, and a migration test that upgrades an old schema and asserts the new code works against it. The open question is timing: which release is the first one that must not break an existing database.
- Multi-file repo edits: v0.2.0 keeps the proposer limited to replacing `train.py`. General repo editing lands with the scale work in v0.4.0, alongside worktrees. That design review settles commit scoping: plan-listed paths vs. an agent-decided commit tool vs. `add -A` with an ignore-file convention for run outputs.
- Compute-node to login-node HTTP egress (gates the epilog webhook).
- Cluster specifics: partition, GPU type, and QoS are not currently set by the executor. Explicit `--partition` and QoS belong with the scale work (v0.4.0); `--time` walltime is pulled forward to v0.2.0.
- Constraint-aware judgment: today judgment scores one metric movement with a confidence measure. Constraint-driven search (e.g. edge models that must fit a size or memory budget) needs a hard gate distinct from the scored objective: keep only if the metric moves AND the run satisfies a budget. Settles where the constraint lives (plan schema field vs. judgment step) and whether it is a per-run gate or a campaign-level rule.
- Frontier exploration: keeping several branch tips alive per campaign instead of one best (idea described in future.md). Settles at the v0.4.0 design review, where worktrees arrive: the pruning rule (when a branch dies: dominated, budget share, age), how the proposer chooses which branch to extend (exploit the leader vs explore the rest), and what `campaign.ended` reports when several branches survive.
