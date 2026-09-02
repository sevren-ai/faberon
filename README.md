# Faberon
Sevren's autonomous ML Research Harness

## Layout

- `packages/control-plane/`: the brain (Python, `uv`-managed, import name `faberon`)
- `docs/design/`: the stable [system design](docs/design/design.md), the living [roadmap](docs/design/roadmap.md), and one doc per release, starting at [v0.1.0](docs/design/v0.1.0.md)
- `CONTRIBUTING.md`: the process rules for every contributor, human or agent
- `AGENTS.md`: agent-specific rules (context loading, writing style), read first by any coding agent

The console (Pi extension, TypeScript) joins as a sibling package in upcoming work.
