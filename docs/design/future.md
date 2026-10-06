# Faberon: Future Improvements

**Status:** living backlog. Speculative ideas and deferred options. Not a commitment to build any of them. Near-term planned work lives in [roadmap.md](roadmap.md); stable architecture in [design.md](design.md).

Add an item when something is worth remembering and clearly not in the current roadmap. Promote an item into the roadmap (and a release doc) when it becomes real planned work.

## Execution backends beyond Slurm

Slurm is the primary path. The executor interface (`submit` / `status` / `cancel`) is the place other backends plug in. The local executor (subprocess on the machine hosting Faberon) is planned work: v0.3.0, see [roadmap.md](roadmap.md).

- **Cloud batch**: adapters for cloud job APIs (for example AWS Batch, GCP Batch).
- **Kubernetes**: Jobs/CronJobs as the execution tier.

## Chat topology

Default is Pi on the login node next to the brain (see [design.md](design.md)).

- **Remote chat interface**: Pi on a laptop (or other machine) talking to Faberon over the network. Needs the API reachable off-host and the optional bearer token.

## CLI configuration

- **`faberon serve --model` flag.** v0.3.0 reads `FABERON_MODEL` only from the environment. A `--model` flag would suit users who swap models between campaigns. The clean path threads the value as an explicit parameter through `create_app_slurm` / `create_app` into the proposer construction (which today reads env in `AgentProposer.from_env`), not by mutating `os.environ` from the CLI. The other `serve` settings stay env-only: the API token and database URL are secrets that must not appear in shell history or `ps` output on a shared login node, and the Slurm account is stable per deployment.

## Observability

- **LLM call tracing via Langfuse.** It could fit as an *addition* alongside Postgres once the agent chassis (Pydantic AI) is in the loop, for tracing the drafter's and judge's LLM calls (token cost, prompt versions, eval scores). Pydantic AI has Langfuse integration. Caveat: Langfuse is either SaaS (needs login-node egress, which is unverified, see [roadmap.md](roadmap.md)) or self-hosted (another service to operate), both of which cut against the minimal-infra, self-hosted-per-deployment stance in [design.md](design.md).

## Collaboration and tenancy

- Multi-user campaigns: per-user identity on events, per-user budgets, approval quorums.

## Durability and scale

- **JSONL mirror of the ledger.** v0.1.0 writes the ledger to Postgres only. A JSONL copy (the portable, human-readable export described in `design.md` §3) is deferred until there's a real consumer: an export job, an off-system reader, or a need to ship events somewhere Postgres doesn't reach. Adding it later is a `Ledger.append` change (write a line alongside the INSERT); the schema and `seq` ordering are unaffected.
- Migrate from DBOS to Temporal if multi-service scale or team-platform needs appear. Same Pydantic AI integration interface; bounded rearchitecture.
- Transient-failure retry policy for the campaign loop. v0.2.0 records the limitation: a submit exception halts the campaign, DBOS resumes on Faberon restart, and the human decides. A bounded retry policy (attempt counts, backoff, and what happens when the retry chain itself fails) needs design before implementation.
- Retention policy for the ledger and run artifacts (what to keep, for how long, and who decides).

## Research loop extensions

- **Frontier exploration: several live branches per campaign.** The v0.2.0 loop keeps a single best: after every round there is one head to build on. The alternative is to keep several branch tips alive and continue experimenting on each reasonable branch, rather than picking a single winner every round. Each run is then judged against its own branch's parent, not against one global best. The ledger's sha and parent sha per experiment already record a tree, and the worktrees planned for v0.4.0 supply the checkout mechanics. Promotion point: the v0.4.0 design review; its open questions are in [roadmap.md](roadmap.md).
- Sandboxed code-writing worker (for example OpenHands SDK) once the agent authors enough experiment code to need containment.
- **Speculative proposal during the wait.** The campaign loop is sequential: propose, submit, poll until the job finishes, judge, propose again. While experiment N runs, the proposer could already design N+1 from N's in-flight commit and cache it. A keep verdict makes the cached proposal the next candidate; a discard throws it away. The ledger only records a proposal once it is committed and run, so speculation itself stays invisible. Promotion point: the v0.4.0 design review, alongside frontier exploration, since both depend on worktrees and both answer what the proposer does while the cluster is busy. Concurrent experiments may absorb most of the win, which argues for settling this after the queue lands.
- In-run probes and actuators (live intervention during training) once post-hoc judgment stops sufficing. Two concrete forms: reading intermediate metric values from the run's output files while it trains, and pulling training curves from an experiment tracker (for example a wandb integration) so the agent can analyze loss curves, not just final scores.
- **Early kill of losing runs.** Once intermediate values or curves are visible (see the probes item), a run that is clearly losing can be cancelled before its walltime, returning the GPU hours to the budget. Matters most for large runs. Needs a judgment rule that acts mid-run (who decides, at what cadence, against which baseline) and executor support: `cancel` already exists in the interface, the open part is the decision policy.
- **Run-length scheduling: cheap probes vs. verification runs.** The plan fixes one walltime for every experiment. The agent could instead choose per experiment: short runs to screen ideas quickly, long runs to verify promising directions. Needs the walltime to become a proposer output (bounded by the plan), budget accounting that reflects the choice, and judgment that does not compare a short probe's metric against a long run's on equal terms.
- Adaptive `sacct` poll interval based on queue-wait estimates.
- Digest cadence and channel for campaign progress.
- Advisory vs. imperative default for injected ideas (imperative mode exists as a config flag; the default is still open).

## Testing

- **Parallel ledger tests.** The ledger tests share one `events` table, cleared per test with `TRUNCATE events RESTART IDENTITY`. That is safe for sequential execution but not for `pytest-xdist`: parallel workers would truncate each other's data. If we adopt xdist, switch the `ledger` fixture to per-test database isolation (each fixture creates and drops a unique `faberon_test_<uuid>` database, so the `Ledger` creates a fresh `events` table and no `TRUNCATE` is needed). Test-only change, no production-code impact.
