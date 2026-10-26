# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Addon: categorized gold ledger for every character, covering quests, world quests, loot,
  vendor, repairs, AH, mail, trade, flights, transmog, barber, training, guild and warband bank.
- Addon: transfers between your own characters are excluded from income and expense totals.
- Addon: `/mp` commands for session, today, last 7 days, net worth by character, and the
  recent ledger.
- Companion: `companion/mariposa.py` imports SavedVariables into SQLite and CSV.
- Companion: `--dashboard` writes an offline HTML dashboard covering net worth, income
  and expenses, category breakdowns, characters, the warband bank, and a filterable ledger.
- Companion: `companion/synth.py` generates synthetic data for development.
- Dashboard: a search box filters the ledger, and Export CSV downloads the filtered ledger.
- Dashboard: a 1-day range that charts today hour by hour and compares it with the same
  time yesterday.
- Dashboard: a Balance by character chart on the Overview, with one line per character in
  its class color, a hover readout of every character's balance, and a table view.
- Addon: crafting orders are tracked as Crafting Orders (the tip paid to place one) and
  Crafting Commissions (earned fulfilling one) instead of Other.
- Addon: gold from opening reward bags and caches, such as Prey hunt rewards, is tracked as
  Reward Bags instead of Other.

### Changed

- Dashboard: laid out like the game's Options window. Reports and characters are in a
  sidebar, the date range is an arrow stepper, totals are shown as Options-style rows, and
  buttons are red. Amounts show coin icons, characters show in their class colors, and the
  tooltip is styled like the game's. It's dark only, like the game, so the light/dark
  toggle is gone.
- Companion: `--summary` prints category names instead of internal keys, in a column wide
  enough for the longest one.

### Fixed

- Addon: net worth no longer reads 0 after logging out. The logout snapshot overwrote the
  warband bank and each character's balance with 0, and the next login then booked the whole
  balance as Untracked Change.
- Companion: resetting a character no longer leaves its old transactions behind, and
  characters deleted from the addon's data are dropped on the next import.
