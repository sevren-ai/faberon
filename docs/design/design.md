# Faberon: System Design

**Status:** stable document. Changes rarely, and only through design review. Planned work, open questions, and the decision log live in [roadmap.md](roadmap.md). Release scopes live in per-version docs (for example [v0.1.0](v0.1.0.md)).

## 1. Purpose

A harness that runs LLM/ML research autonomously: it proposes experiments, submits training jobs to Slurm, waits durably for results, judges them against stated expectations, and decides what to try next. Every decision is recorded in an auditable ledger, and humans can steer the system at any time.

Requirements:
* **autonomy**: end-to-end agent loop
* **cluster-native**: first-class Slurm
* **durability**: survives restarts and reboots; hours-to-days waits cost nothing while sleeping
* **auditability**: append-only event ledger
* **human steering**: goal up front, ideas mid-run, gates on high-impact actions

Terminology:
* A **campaign** is one autonomous research run end-to-end, from intake to budget exhaustion or stop condition.
* The **drafter** (console-side, no autonomous authority) interviews the human and drafts the **plan** (research plan: goal, metric command, scope, budget, stop conditions, judgment rules, approval policy)
* The **loop** then runs experiments under the plan until the campaign ends.

## 2. Architecture

Three tiers connected by explicit contracts (typed JSON over HTTP/SSE, plus JSONL files). Any tier is replaceable without touching the others.

```
┌───────────────────┐      REST + SSE     ┌────────────────────────────────┐
│ Console           │◄──(bearer token────►│ Control plane: the only brain  │
│ (Pi ext., TS;     │    once off-host)   │ Pydantic AI · DBOS · FastAPI   │
│ hosts the drafter)│                     │ · Postgres · on the login node │
└───────────────────┘                     └──────┬───────────────▲─────────┘
                                          submit ▼ local sbatch  │ sacct poll
                                          ┌────────────────────────────────┐
                                          │ Slurm cluster (execution)      │
                                          └────────────────────────────────┘
```

- **Control plane**: the only component with autonomous authority. A Pydantic AI agent (typed tools, schema validation) wrapped in DBOS Transact (durable execution: step checkpoints, replay-on-restart, durable sleep, `send`/`recv`, queues) behind a FastAPI app. Postgres is the only infrastructure. The control plane runs on the cluster login node, so Slurm calls are local subprocesses with no SSH transport.
- **Console**: a Pi extension. Hosts the drafter, live status, idea injection, and approvals. It reasons conversationally, but every write is a human-initiated API call.
- **Execution**: the Slurm cluster.

Design rule: **one brain**. The console and the drafter propose; the brain disposes; the ledger remembers.

**Deployment model.** Self-hosted per deployment. All state (Postgres, JSONL, notes, artifacts) lives on the operator's machines, and there is no central Faberon server. Trust is single-operator: one optional bearer token (`FABERON_API_TOKEN`) guards the API once it is reachable off-host, which happens early since console and brain typically run on different machines. Multi-user is deferred. Dev loop: workstation → GitHub → login node.

## 3. Key Mechanisms

**Durable Slurm loop.** Workflow: submit (idempotent, dedup-keyed) → wait → judge → decide next. Completion detection is **poll-first** (`DBOS.sleep` + local `sacct`) because compute-node to login-node HTTP egress is unverified. The Slurm-epilog `curl` webhook (`DBOS.send` → `recv`) drops in later as a fast path with no workflow changes. The executor sits behind a narrow `submit`/`status`/`cancel` interface: the real Slurm adapter first, a fake-subprocess shim for off-cluster unit tests. A DBOS queue (`concurrency=N`) caps parallel jobs.

**Event ledger.** Append-only, dual-written: Postgres (queryable) plus JSONL (portable). Families: `campaign.*`, `experiment.*`, `intervention.*`, `idea.injected`, `expectation.judged`, `budget.*`, `approval.*`. Every event carries actor, justification, and a plan-clause reference. The ledger, plus a living research-notes file, is the source of truth a fresh agent re-orients from. No process's memory is authoritative.

**Why not JSONL-only?** (1) Durability *is* Postgres: DBOS checkpoints every step, sleep, and signal there, and files would mean re-implementing durable execution. (2) The design needs atomicity (dedup keys, queue-slot claims, exactly-once on retry), which files cannot provide, especially on the NFS home directories typical of login nodes. (3) The ledger is queried ("what worked, budget burned"), not just read. JSONL stays as the portable copy.

**Campaign bootstrap.** The drafter's intake produces the plan. Control-plane validation is the sole acceptance gate. Approval writes `campaign.created` and starts the loop. Amendments are events (`campaign.amended`), never edits: runs are judged against the rules in force at their time.

**Human steering.** `POST /campaigns/{id}/ideas` wraps `DBOS.send`: the idea lands in the ledger and the agent weighs it at its next decision boundary. Advisory is the default; an imperative mode that forces execution is a config flag, recorded per event. Approvals for gated actions use the same signal path. Human and agent actions are the same kind of event.

**Judgment.** Each experiment's hypothesis and expected metric movement are recorded up front. Outcomes are scored with a robust confidence measure (e.g. MAD-based) before keep/discard. Optional eval-suite non-regression acts as backpressure.

## 4. External API (v0)

"v0" is the contract version, independent of release versions: v0 means unstable while we learn, v1 is the first stability promise. Routes are prefixed `/v0/` from day one so a future `/v1` can coexist with it.

`POST /campaigns` · `POST /campaigns/{id}/ideas` · `POST /campaigns/{id}/amendments` · `POST /approvals/{id}` · `GET /campaigns` · `GET /campaigns/{id}` · `GET /campaigns/{id}/runs` · `GET /runs/{id}` · `GET /events` (SSE ledger tail).

Contracts are **skeleton-first**: shapes live as Pydantic models in one quarantined module from day one and are frozen into versioned artifacts (JSON Schema / OpenAPI goldens) after Phase 1. This contract keeps console and brain independently replaceable.

## 5. Technology Choices

| Concern | Choice | Rationale                                                                                                                                                                           |
|---|---|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Core language | Python 3.14, `uv` | ML stack, experiment code, and eval tooling are Python; the chosen agent chassis is Python-only.                                                                                    |
| Agent chassis | Pydantic AI | Typed tools, boundary validation, durable-execution integrations.                                                                                                                   |
| Durability | DBOS Transact (MIT) | Durable sleep, signals, SQL state, flow-controlled queues, step audit, with only Postgres to operate. Youngest dependency, mitigated by the tier boundaries and operator-owned state. |
| Console | Pi extension (TS) | Open-source (MIT), European, extensible; npm-distributed. Replaceable through the API contract.                                                                                     |
| Models | Provider-agnostic env config (`FABERON_MODEL`) | Local/open models first-class. Tests use `TestModel`.                                                                                                     |
| Database | Postgres via `FABERON_DATABASE_URL` | Native install on dev machines; scripted userspace install (no root) on login nodes.                                                                |
| Scale-up path | Temporal | Same Pydantic AI integration interface; only on genuine scale triggers.                                                                                                             |
