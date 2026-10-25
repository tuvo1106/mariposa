# ADR-0003: SavedVariables plus a companion importer for offline data

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

The goal is offline dashboards, but WoW addons have no file or network I/O. The only data
that leaves the game is SavedVariables, a Lua file written on logout or `/reload`.

## Decision

Store an append-only, per-character, sequence-numbered ledger in account-wide SavedVariables.
A standard-library Python script parses the file and upserts it into SQLite, keyed by
`(character, seq)`, so re-running it is safe and history survives future in-game pruning.

## Alternatives considered

| Option | Why not |
|---|---|
| In-game export string (copy/paste) | Manual every time; worth adding later as a convenience, not as the pipeline. |
| Third-party Lua parser (`slpp`, `luadata`) | SavedVariables is a small Lua subset; a ~100-line parser avoids a dependency and handles WoW's byte-string encoding explicitly. |
| Dashboard reads the `.lua` file directly | Loses history once old transactions are pruned in game, and ties every dashboard to Lua parsing. |

## Consequences

Data reaches dashboards only after a logout or `/reload`, and a client crash loses that
session's categories. The SQLite file is the durable history, so it's the thing to back up.
