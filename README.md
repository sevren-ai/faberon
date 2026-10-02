# Faberon

[Sevren](https://sevren.ai)'s autonomous ML research harness.

Faberon runs LLM/ML research autonomously. Give it a research plan (goal, metric, budget, stop conditions) and it proposes experiments, submits training jobs, waits for results, judges them against your expectations, and decides what to try next. Every decision lands in an append-only ledger, and you can steer it mid-run.

Three tiers, one contract:

- The **brain** is the only component with autonomous authority: a durable agent loop behind a small HTTP API, with Postgres as its only infrastructure.
- The **console** is a Pi extension for drafting plans and steering campaigns from a chat session.
- The **CLI** covers the same operations from a shell (no LLM).

The console and the CLI propose, the brain decides, the ledger remembers. 
```
     ┌───────────┐   ┌─────────────┐
     │ Console   │   │ CLI         │
     │ (Pi, TS)  │   │ (Typer, Py) │
     └───────────┘   └─────────────┘
        │                  │
        └────────┬─────────┘
                 │  v0 API (HTTP + SSE, bearer token)
        ┌────────┴───────────────────────────┐
        │ Brain: the only authority          │
        │    Pydantic AI, DBOS, FastAPI      │
        │    Postgres (ledger)               │
        └────────────┬───────────┬───────────┘
              submit ▼           ▲ status
        ┌────────────┴───────────┴───────────┐
        │ Executors (submit/status/cancel):  │
        │  · Slurm cluster                   │
        │  · local subprocess                │
        └────────────────────────────────────┘
```

## Install

Pick the guide for your machine:

- [Install on a workstation](docs/install-workstation.md): you have sudo.
- [Install on a login node](docs/install-login-node.md): shared cluster node, no sudo.

To work on the Faberon repo itself, see [docs/developing.md](docs/developing.md).

## Quickstart

With the brain running (`faberon serve`) and `FABERON_API_TOKEN` set, submit a campaign and watch it:

```bash
faberon create plan.json   # submit a research plan
faberon list               # campaigns and live status
faberon events <id> -f     # stream the ledger live
faberon cancel <id>        # stop at the next decision boundary
```

Or do the same from a Pi chat session with the console extension loaded: ask it to list campaigns, inject an idea, draft a plan, etc.

Both clients talk to the brain over a small HTTP API (`/v0/*`, bearer token). A running brain serves its live API reference at `/docs`.


## Feedback and contributing

- Found a bug? File an [issue](https://github.com/sevren-ai/faberon/issues).
- Have a feature idea? Post a new thread in the [discussion forum](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests). For now we are not accepting feature pull requests.
- Ran Faberon and got some cool results? [Tell us](https://github.com/sevren-ai/faberon/discussions/categories/show-and-tell) all about it!
- Have a question or ran into a problem not covered by our [troubleshooting guide](docs/troubleshooting.md)? Ask it [here](https://github.com/sevren-ai/faberon/discussions/categories/q-a)!

For contributors and maintainers, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
