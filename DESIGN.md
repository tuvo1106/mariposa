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
  version = 1,
  settings = { debug = false },
  warband = { gold = <copper>, updated = <epoch> },
  chars = {
    ["Name-NormalizedRealm"] = {
      name, realm, class, faction, level, gold, lastSeen,
      seq = <last tx number>,
      tx = { { s = seq, t = epoch, a = copper (signed), k = category, r = ref?, m = mapID? }, ... },
    },
  },
}
```

Each character's ledger is append-only and numbered, so `(character, seq)` is a stable key
for idempotent imports. Categories are defined in `Mariposa/Categories.lua`.

## Companion

`companion/mariposa.py` finds every `WTF/Account/*/SavedVariables/Mariposa.lua` (one per WoW
license), parses it with a small SavedVariables-subset Lua parser, and upserts it into
SQLite (`characters`, `transactions`, `warband`). Dashboards read the SQLite file.

## Roadmap

1. **Ledger MVP** (done): attribution, multi-character storage, `/mp` summaries, importer.
2. **Dashboard**: Streamlit or a static page over `mariposa.db`.
3. **Transfers & net worth polish**: trade-with-alt detection, net-worth history.
4. **In-game UI**: LibDataBroker button, ledger window with re-categorizing, goals.
5. **Retention**: roll old transactions into daily totals to bound SavedVariables size.
   AH profit per item from mail invoices.

## Known limits

- SavedVariables are lost if the client crashes; the login `adjustment` keeps balances
  right but loses the categories.
- AH outbid refunds arrive as plain mail and currently land in `mail_in`.
- Midnight restricts some data during instanced combat. `PLAYER_MONEY` isn't affected, but
  verify loot attribution inside dungeons.
