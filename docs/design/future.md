# Faberon: Future Improvements

**Status:** living backlog. Speculative ideas and deferred options. Not a commitment to build any of them. Near-term planned work lives in [roadmap.md](roadmap.md); stable architecture in [design.md](design.md).

Add an item when something is worth remembering and clearly not in the current roadmap. Promote an item into the roadmap (and a release doc) when it becomes real planned work.

## Execution backends beyond Slurm

Slurm is the primary path. The executor interface (`submit` / `status` / `cancel`) is the place other backends plug in.

- **Local executor**: run the training script as a subprocess on the machine hosting Faberon. Serves users without a cluster, and makes full-loop development possible on a workstation.
- **Cloud batch**: adapters for cloud job APIs (for example AWS Batch, GCP Batch).
- **Kubernetes**: Jobs/CronJobs as the execution tier.

## Console topology

Default is Pi on the login node next to the brain (see [design.md](design.md)).

- **Remote console**: Pi on a laptop (or other machine) talking to the control plane over the network. Needs the API reachable off-host and the optional bearer token.

## Collaboration and tenancy

- Multi-user campaigns: per-user identity on events, per-user budgets, approval quorums.

## Durability and scale

- Migrate from DBOS to Temporal if multi-service scale or team-platform needs appear. Same Pydantic AI integration interface; bounded rearchitecture.
- Retention policy for the ledger and run artifacts (what to keep, for how long, and who decides).

## Research loop extensions

- Sandboxed code-writing worker (for example OpenHands SDK) once the agent authors enough experiment code to need containment.
- In-run probes and actuators (live intervention during training) once post-hoc judgment stops sufficing.
- Adaptive `sacct` poll interval based on queue-wait estimates.
- Digest cadence and channel for campaign progress.
- Advisory vs. imperative default for injected ideas (imperative mode exists as a config flag; the default is still open).
