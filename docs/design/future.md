# Faberon: Future Improvements

**Status:** living backlog. Speculative ideas and deferred options. Not a commitment to build any of them. Near-term planned work lives in [roadmap.md](roadmap.md); stable architecture in [design.md](design.md).

Add an item when something is worth remembering and clearly not in the current roadmap. Promote an item into the roadmap (and a release doc) when it becomes real planned work.

## Execution backends beyond Slurm

Slurm is the primary path. The executor interface (`submit` / `status` / `cancel`) is the place other backends plug in. The local executor (subprocess on the machine hosting Faberon) is planned work: v0.4.0, see [roadmap.md](roadmap.md).

- **Cloud batch**: adapters for cloud job APIs (for example AWS Batch, GCP Batch).
- **Kubernetes**: Jobs/CronJobs as the execution tier.

## Console topology

Default is Pi on the login node next to the brain (see [design.md](design.md)).

- **Remote console**: Pi on a laptop (or other machine) talking to the control plane over the network. Needs the API reachable off-host and the optional bearer token.

## Observability

- **LLM call tracing via Langfuse.** It could fit as an *addition* alongside Postgres once the agent chassis (Pydantic AI) is in the loop, for tracing the drafter's and judge's LLM calls (token cost, prompt versions, eval scores). Pydantic AI has Langfuse integration. Caveat: Langfuse is either SaaS (needs login-node egress, which is unverified, see [roadmap.md](roadmap.md)) or self-hosted (another service to operate), both of which cut against the minimal-infra, self-hosted-per-deployment stance in [design.md](design.md).

## Collaboration and tenancy

- Multi-user campaigns: per-user identity on events, per-user budgets, approval quorums.

## Durability and scale

- **JSONL mirror of the ledger.** v0.1.0 writes the ledger to Postgres only. A JSONL copy (the portable, human-readable export described in `design.md` §3) is deferred until there's a real consumer: an export job, an off-system reader, or a need to ship events somewhere Postgres doesn't reach. Adding it later is a `Ledger.append` change (write a line alongside the INSERT); the schema and `seq` ordering are unaffected.
- Migrate from DBOS to Temporal if multi-service scale or team-platform needs appear. Same Pydantic AI integration interface; bounded rearchitecture.
- Transient-failure retry policy for the campaign loop. v0.2.0 records the limitation: a submit exception halts the campaign, DBOS resumes on control-plane restart, and the human decides. A bounded retry policy (attempt counts, backoff, and what happens when the retry chain itself fails) needs design before implementation.
- Retention policy for the ledger and run artifacts (what to keep, for how long, and who decides).

## Research loop extensions

- **Frontier exploration: several live branches per campaign.** The v0.2.0 loop keeps a single best: after every round there is one head to build on. The alternative is to keep several branch tips alive and continue experimenting on each reasonable branch, rather than picking a single winner every round. Each run is then judged against its own branch's parent, not against one global best. The ledger's sha and parent sha per experiment already record a tree, and the worktrees planned for v0.5.0 supply the checkout mechanics. Promotion point: the v0.5.0 design review; its open questions are in [roadmap.md](roadmap.md).
- Sandboxed code-writing worker (for example OpenHands SDK) once the agent authors enough experiment code to need containment.
- In-run probes and actuators (live intervention during training) once post-hoc judgment stops sufficing.
- Adaptive `sacct` poll interval based on queue-wait estimates.
- Digest cadence and channel for campaign progress.
- Advisory vs. imperative default for injected ideas (imperative mode exists as a config flag; the default is still open).

## Testing

- **Parallel ledger tests.** The ledger tests share one `events` table, cleared per test with `TRUNCATE events RESTART IDENTITY`. That is safe for sequential execution but not for `pytest-xdist`: parallel workers would truncate each other's data. If we adopt xdist, switch the `ledger` fixture to per-test database isolation (each fixture creates and drops a unique `faberon_test_<uuid>` database, so the `Ledger` creates a fresh `events` table and no `TRUNCATE` is needed). Test-only change, no production-code impact.
