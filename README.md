# Faberon

[Sevren](https://sevren.ai)'s autonomous ML research harness.

Faberon runs LLM/ML research autonomously. Give it a research plan (goal, metric, budget, stop conditions) and it proposes experiments, submits training jobs, waits for results, judges them against your expectations, and decides what to try next. Every decision is recorded in an append-only ledger, and you can steer it mid-run.

Three tiers:

- The **brain** is the main component with autonomous authority: a durable agent loop behind a small HTTP API
- The **chat** interface ("Faberon Chat") is a Pi extension for drafting plans and steering campaigns from a chat session
- The **CLI** covers the same operations from a shell (no LLM)

The chat interface and the CLI propose, the brain decides, the ledger remembers.
```
     +-----------+   +-------------+
     | Chat      |   | CLI         |
     | (Pi, TS)  |   | (Typer, Py) |
     +-----------+   +-------------+
        |                  |
        +--------+---------+
                 |  API
        +--------+---------------------------+
        | Brain: authority                   |
        |    Pydantic AI, DBOS, FastAPI      |
        |    Postgres (ledger), uvicorn      |
        +------------+-----------+-----------+
              submit v           ^ status
            +--------+-----------+-------------+
            | Executors                        |
            |  - Slurm cluster                 |
            |  - local subprocess              |
            +----------------------------------+
```

## Install

### Prerequisites
Pick the guide for your machine:
- [Install on a workstation](docs/install-workstation.md): you have sudo
- [Install on a login node](docs/install-login-node.md): no sudo (e.g. cluster login node)


### Brain & chat
From PyPI and npm (once these are available):

```bash
uv venv
uv pip install faberon

npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install npm:@faberon/chat
```

or from source:
```bash
git clone https://github.com/sevren-ai/faberon
cd faberon
uv tool install packages/brain
npm --prefix packages/chat ci --legacy-peer-deps
```

## Quickstart

> For a complete runbook using v0.3.0 on a local workstation, see https://github.com/sevren-ai/faberon/discussions/61

Start the API inside `tmux` or `screen` so it survives your SSH session:

```bash
faberon serve
```

With the brain running, submit a campaign and watch it through the CLI:

```bash
faberon create plan.json my_repo  # start a campaign with a given plan for a specific repo
faberon list                      # list all campaigns with their live status
faberon show <id>                 # show the details of one particular campaign
faberon events <id> -f            # stream the events of one particular campaign
faberon cancel <id>               # cancel one particular campaign
```

Or do the same from a Pi chat session with the Faberon Chat extension loaded: ask it to list campaigns, inject an idea, draft a plan, etc.

```bash
pi
```

or (from source)

```bash
bash scripts/chat.sh
```

Do not run bare `npx pi` from the repo root: npx falls back to the unrelated `pi` package on npm.

The chat interface and CLI speak to the same API; use whichever suits the moment.

## Future work

The following features are not implemented yet but are planned as future work in the very near future:
- Editing multiple files, and not just Python

## Feedback and contributing

- Found a bug? File an [issue](https://github.com/sevren-ai/faberon/issues).
- Have a feature idea (that is not yet planned for)? Post a new thread in the [discussion forum](https://github.com/sevren-ai/faberon/discussions/categories/feature-requests). For now we are not accepting feature pull requests.
- Ran Faberon and got some cool results? [Tell us](https://github.com/sevren-ai/faberon/discussions/categories/show-and-tell) all about it!
- Have a question or ran into a problem not covered by our [troubleshooting guide](docs/troubleshooting.md)? Ask it [here](https://github.com/sevren-ai/faberon/discussions/categories/q-a)!

For contributors and maintainers, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

The software is provided "as is" without warranty of any kind, under an MIT [LICENSE](LICENSE).
