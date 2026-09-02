# Faberon: Roadmap

**Status:** living document. Contains the features planned for the near future, plus open questions. Updated whenever plans or decisions change, by humans or by agents (see `AGENTS.md`). Stable architecture and rationale live in [design.md](design.md). This doc is not a history: git records what shipped and why.

**Current focus:** v0.1.0, the skeleton. Scope and PR sequence: [v0.1.0.md](v0.1.0.md).

## Phases

A version is a milestone release, not the whole roadmap. Each phase becomes its own version with its own design doc when its design review happens.

- **Phase 0: scaffold.** `uv` monorepo (console package joins as sibling in Phase 2); quarantined schema module; Postgres setup scripts for dev machine and login node.
- **Phase 1: skeleton.** One thin path through every tier. Ships as **v0.1.0**.
- **Phase 2: console v0.1 (planned v0.2.0).** Pi extension: drafter intake, `inject_idea`, `runs_status`, `approve`, live SSE widget (runs, budget burn, pending approvals).
- **Phase 3: scale and safety (planned v0.3.0).** Concurrency-limited queue for ablations; budget caps and approval gates; epilog webhook once egress is verified; restart drills as routine.
- **Phase 4: research policy (planned v0.4.0).** The full propose → run → judge → keep/discard loop with agent-authored `train.py` edits; living notes file; plan stop-conditions honored end-to-end.
- **Phase 5 (as needed).** Sandboxed code-writing worker; in-run probes/actuators; Temporal migration. Conditional on real triggers, may never ship.

## Open Questions

- Advisory vs. imperative default for injected ideas; digest cadence and channel.
- Compute-node to login-node HTTP egress (gates the epilog webhook).
- Cluster specifics: partition, GPU type/count, account/QoS, walltime limits; login-node internet for data prep.
- Whether the poll interval should adapt to queue-wait estimates.
