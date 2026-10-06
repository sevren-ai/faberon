# Design documents

- [design.md](design.md): the stable system design. Changes rarely, and only through design review.
- [roadmap.md](roadmap.md): features planned for the near future, plus open questions that affect that work.
- [future.md](future.md): speculative ideas and deferred options. Not a commitment to build them.
- `vX.Y.Z.md`: one doc per release, containing only what that release ships. A doc freezes the moment its release ships and is then moved to `archive/`.

## Rules for release docs

- A release doc names only its own version and past versions. It must not name future versions by number: numbers change as the roadmap shifts, and a frozen doc cannot be corrected. Refer to future work as "future work", "a later release", or point at [roadmap.md](roadmap.md) or [future.md](future.md). Past-version references are fine (for example "the v0.2.1 re-seed recovery").
