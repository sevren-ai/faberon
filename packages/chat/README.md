# Faberon Chat

The chat interface of [Faberon](https://github.com/sevren-ai/faberon), an autonomous ML research harness.

Faberon Chat is a [Pi](https://github.com/earendil-works/pi-coding-agent) extension for operating Faberon campaigns from a chat session: draft a research plan conversationally, submit it, watch proposals and judgments stream in live, inject ideas mid-run, and cancel campaigns. Every write goes through the brain's HTTP API; the chat interface proposes, the brain decides.

The brain ships separately as [faberon](https://pypi.org/project/faberon/) on PyPI and provides the `faberon` CLI, which covers the same operations from a shell.

## Install

Requires a running Faberon brain and the Pi CLI.

```bash
pi install npm:@faberon/chat
```

## Documentation

Install guides, quickstart, runbooks, and design docs live in the [repo](https://github.com/sevren-ai/faberon).

## Status

Early beta: expect rough edges and breaking changes.

## License

MIT
