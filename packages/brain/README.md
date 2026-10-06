# Faberon brain

The brain of [Faberon](https://github.com/sevren-ai/faberon), an autonomous ML research harness.

Give Faberon a research plan and it proposes experiments, submits training jobs (Slurm cluster or local machine), waits for results, judges them against your expectations, and decides what to try next. Every decision lands in an append-only Postgres ledger, and you can steer a running campaign at any time.

This package provides the brain: the durable agent loop (Pydantic AI + DBOS) behind a FastAPI HTTP API, plus the `faberon` CLI for operating campaigns from a shell. The chat interface ships separately as [@faberon/chat](https://www.npmjs.com/package/@faberon/chat).

## Install

Requires Python 3.14 and a Postgres database.

```bash
uv pip install faberon
faberon serve
```

## Documentation

Install guides, quickstart, runbooks, and design docs live in the [repo](https://github.com/sevren-ai/faberon).

## Status

Early beta: expect rough edges and breaking changes.

## License

MIT
