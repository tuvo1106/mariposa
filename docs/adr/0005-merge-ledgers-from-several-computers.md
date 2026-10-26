# ADR-0005: Merge ledgers from several computers in the companion

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

WoW doesn't sync SavedVariables between computers, so playing on two of them leaves two
`Mariposa.lua` files that each know only what happened locally. The same character can be
played on both. That breaks two assumptions:

- `(character, seq)` stopped being unique. Each computer numbers a character's transactions
  on its own, so two files collide, and the importer's reset detection reads the second file
  as a reset and replaces the first ledger.
- Money gets counted twice. After a character is played on the laptop, the desktop's next
  login sees a different balance and books the whole difference as an `adjustment`, while
  the laptop recorded the same money transaction by transaction.

## Decision

- The addon gives each SavedVariables file an `installId`, and stores `p` on each login
  adjustment: when this computer last saw the character.
- The companion keys transactions by `(character, source, seq)`, where `source` is the
  `installId`. Files from addon versions without one use where they were read from.
- Files copied by hand into `imports/` are read alongside the local WTF folder. A file in a
  subfolder belongs to the account it's named after; a loose file belongs to the single
  local account.
- `reconcile()` sets each adjustment's `explained` to the sum of other sources'
  transactions for that character between `p` and the login. Reports read the `ledger`
  view, which subtracts it and drops fully explained adjustments.
- A character's balance comes from whichever source saw it most recently, as does the
  warband bank.
- An identical transaction filed under another source is treated as the same one and
  re-filed. That migrates pre-`installId` rows, including the v0 database's, and makes a
  renamed import harmless.

## Alternatives considered

| Option | Why not |
|---|---|
| In-game export/import string | Still manual every time, needs a compression library, and the addon would have to merge foreign ledgers into its own SavedVariables. |
| Sync the WTF folder with a cloud drive | Two clients write the same file; whichever logs out last overwrites the other. |
| Drop all adjustments when there are several sources | Throws away real untracked gold, such as from sessions with the addon disabled. |
| Rebuild the database on schema change | The database is the durable history (ADR-0003); a migration keeps it. |

## Consequences

Each computer's ledger survives intact and merges in any order, any number of times. In
game, `/mp` still reflects only the local computer, and its first login after playing
elsewhere shows the adjustment. Adjustments from files without `p` fall back to this
source's previous transaction as the start of the gap, clamped so they can shrink but never
flip sign. Imports are durable: deleting a file from `imports/` doesn't remove its data.
