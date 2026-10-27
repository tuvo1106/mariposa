# Mariposa design

## Goal

A personal-finance-style ledger (in the spirit of Monarch) for WoW gold: every gold change on
every character, categorized, with transfers between your own characters kept out of
income/expense totals. The end goal is offline dashboards; the in-game UI is secondary.

## How money gets attributed

WoW reports *that* gold changed (`PLAYER_MONEY` / `GetMoney()`), never *why*. Mariposa
infers the reason from what happened around the change, in this order
([ADR-0002](docs/adr/0002-attribute-money-by-expectations-then-context.md)):

1. **Expectations.** Hooks and events announce money they know is coming:
   - `QUEST_TURNED_IN` gives the exact reward. `C_QuestLog.IsWorldQuest` / `IsQuestTask`
     split out world quests and bonus objectives.
   - `TakeInboxMoney` / `AutoLootMailItem`: `GetInboxInvoiceInfo` identifies AH sales.
     A sender from your own roster makes it a transfer.
   - `SendMail`: money sent plus postage. A recipient from your own roster makes it a transfer.
   - `C_Bank.DepositMoney` / `WithdrawMoney` and the guild-bank equivalents.
   - `RepairAllItems` and AH posting (amount unknown, so these claim the next change in
     their direction).
2. **Context.** Whatever is left is attributed to the open window (merchant, AH, mail,
   trade, flight master, …), with a 2 s grace after it closes.
3. **Fallback.** `other`, recorded with the zone's map ID so it can be re-categorized later.

Changes landing within 0.3 s are batched, so a quest reward and loot that arrive together
are split correctly.

On login, any gap between the saved and actual balance is booked as `adjustment`, so
balances reconcile even after a crash or a session with the addon disabled.

## Storage

Account-wide SavedVariables `MariposaDB`, written by the game only on logout or `/reload`
([ADR-0003](docs/adr/0003-savedvariables-plus-companion-importer.md)):

```lua
MariposaDB = {
  version = 3,
  installId = "<hex>",   -- this computer's copy of the data
  questNames = { [questID] = "Title", ... },  -- titles for quest rewards' details
  settings = { debug = false },
  warband = { gold = <copper>, updated = <epoch> },
  chars = {
    ["Name-NormalizedRealm"] = {
      name, realm, class, faction, level, gold, lastSeen,
      seq = <last tx number>,
      tx = { { s = seq, t = epoch, a = copper (signed), k = category, r = ref?, m = mapID?,
               p = lastSeen before this login? (adjustments only) }, ... },
    },
  },
}
```

Each character's ledger is append-only and numbered per install, so `(character, install,
seq)` is a stable key for idempotent imports. A quest reward's `r` is the quest ID. Its title
goes in `questNames` when the game has it, and on each login the addon asks the game to load
any titles still missing, so earlier rewards get named too. A crafting commission's `r` is
the item and customer. Categories are defined in
`Mariposa/Categories.lua`.

## Companion

`companion/mariposa.py` finds every `WTF/Account/*/SavedVariables/Mariposa.lua` (one per WoW
license), parses it with a small SavedVariables-subset Lua parser, and upserts it into
SQLite (`characters`, `transactions`, `warband`). Dashboards read the SQLite file through
the `ledger` view.

It also reads `Mariposa.lua` files copied from other computers into `imports/`, and merges
them ([ADR-0005](docs/adr/0005-merge-ledgers-from-several-computers.md)). Each computer's
ledger is kept separately. A character's balance comes from whichever computer saw it last,
and so does the warband bank. A login `adjustment` is reduced by whatever another computer
recorded for that character while this one wasn't watching, so money is counted once.

## Dashboard

`--dashboard` writes one self-contained HTML file: the data is embedded as JSON and the
charts are hand-built SVG, so it opens offline with no server
([ADR-0004](docs/adr/0004-static-html-dashboard.md)). It shows net worth, income, expenses,
net and per-day averages against the previous period, a net-worth line, daily income and
expense columns, breakdowns by category, a per-character table, and the ledger. Everything
can be filtered by date range and character.

It's laid out like the game's Options window and is dark only, like the game. A sidebar
lists the report pages (Overview, Income & Expenses, Characters, Ledger) and the characters,
and the selected character filters every page. The date range is an arrow stepper, a search
box filters the ledger, and Export CSV downloads the filtered ledger. Money shows with coin
icons and character names in their class colors. The chart colors (rare-item blue for
income, red for expenses) pass colorblind-separation and contrast checks against the panel
background. Bright gold and uncommon-item green don't, so gold is kept to single-series
accents like the net-worth line and headings. Titles use Friz Quadrata or Cinzel if
installed, and otherwise fall back to Palatino or Georgia, so nothing is fetched.

The warband bank is treated as its own **pocket**, alongside the characters. Deposits are
only recorded on the character side, so `dashboard.py` mirrors each one onto the warband.
Transfers then net to zero across all pockets, and any pocket's balance history is its
current balance minus later transactions.

`companion/synth.py` generates a realistic synthetic `Mariposa.lua` for development.

## Roadmap

1. **Ledger MVP** (done): attribution, multi-character storage, `/mp` summaries, importer.
2. **Dashboard** (done): static offline HTML over `mariposa.db`, plus synthetic data.
3. **Transfers & net worth polish**: trade-with-alt detection, net-worth history.
4. **In-game UI**: LibDataBroker button, ledger window with re-categorizing, goals.
5. **Retention**: roll old transactions into daily totals to bound SavedVariables size.
   AH profit per item from mail invoices.

## Known limits

- SavedVariables are lost if the client crashes; the login `adjustment` keeps balances
  right but loses the categories.
- AH outbid refunds arrive as plain mail and currently land in `mail_in`.
- Merging computers happens only in the companion. In game, `/mp` summaries cover what this
  computer recorded, and the first login after playing elsewhere shows an adjustment.
- Midnight restricts some data during instanced combat. `PLAYER_MONEY` isn't affected, but
  verify loot attribution inside dungeons.
