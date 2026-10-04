# Faberon

[Sevren](https://sevren.ai)'s autonomous ML research harness.

Faberon runs LLM/ML research autonomously. Give it a research plan (goal, metric, budget, stop conditions) and it proposes experiments, submits training jobs, waits for results, judges them against your expectations, and decides what to try next. Every decision is recorded in an append-only ledger, and you can steer it mid-run.

Three tiers, one contract:

- The **brain** is the only component with autonomous authority: a durable agent loop behind a small HTTP API
- The **console** is a Pi extension for drafting plans and steering campaigns from a chat session
- The **CLI** covers the same operations from a shell (no LLM)

The console and the CLI propose, the brain decides, the ledger remembers. 
```
     ┌───────────┐   ┌─────────────┐
     │ Console   │   │ CLI         │
     │ (Pi, TS)  │   │ (Typer, Py) │
     └───────────┘   └─────────────┘
        │                  │
        └────────┬─────────┘
                 │  API
        ┌────────┴───────────────────────────┐
        │ Brain: authority                   │
        │    Pydantic AI, DBOS, FastAPI      │
        │    Postgres (ledger)               │
        └────────────┬───────────┬───────────┘
              submit ▼           ▲ status
            ┌────────┴───────────┴──────┐
            │ Executors                 │
            │  · Slurm cluster          │
            │  · local subprocess       │
            └───────────────────────────┘
```

## Install

### Prerequisites
Pick the guide for your machine:
- [Install on a workstation](docs/install-workstation.md): you have sudo
- [Install on a login node](docs/install-login-node.md): no sudo (e.g. cluster login node)


### Brain & console
From Pypi and npm (once these are available):

```bash
uv venv
uv pip install faberon

npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install npm:@faberon/console
```

or from source:
```bash
git clone https://github.com/sevren-ai/faberon
cd faberon
uv tool install packages/control-plane
npx pi -e packages/console/src/index.ts
```

## Quickstart

Start the API inside `tmux` or `screen` so it survives your SSH session:

```bash
faberon serve
```

With the brain running, submit a campaign and watch it through the CLI:

```bash
faberon create plan.json   # start a campaign from a given research plan
faberon list               # list all campaigns with their live status
faberon show <id>          # show the details of one particular campaign
faberon events <id> -f     # stream the events of one particular campaign
faberon cancel <id>        # cancell one particular campaign
```

Or do the same from a Pi chat session with the console extension loaded: ask it to list campaigns, inject an idea, draft a plan, etc.

```bash
pi
```

or (from source)

```bash
pi -e packages/console/src/index.ts
```

The console and CLI speak to the same API; use whichever suits the moment.

## Feedback and contributing

- Found a bug? File an [issue](https://github.com/sevren-ai/faberon/issues).
- Have a feature idea? Post a new thread in the [discussion forum](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests). For now we are not accepting feature pull requests.
- Ran Faberon and got some cool results? [Tell us](https://github.com/sevren-ai/faberon/discussions/categories/show-and-tell) all about it!
- Have a question or ran into a problem not covered by our [troubleshooting guide](docs/troubleshooting.md)? Ask it [here](https://github.com/sevren-ai/faberon/discussions/categories/q-a)!

For contributors and maintainers, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
