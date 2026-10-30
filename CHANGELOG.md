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
- Dashboard: selecting a category on Income & Expenses opens the Ledger filtered to it,
  within the current date range and character.
- Addon: quest rewards show the quest's name instead of its ID, including rewards recorded
  before this change, which are named after your next login.
- Crafting commissions record the profession, item, and customer, and Income & Expenses
  breaks Crafting Commissions down by profession.
- Companion: data from other computers. Copy their `Mariposa.lua` into `imports/`, and their
  ledgers are merged without counting the same gold twice. The addon now identifies each
  computer's data, and the database is migrated in place.
- Addon: `/mp forget Name` deletes a character's ledger and stops tracking it; `/mp track`
  resumes. The importer drops forgotten characters from the database.
- Dashboard: Hide/Show buttons in the sidebar leave a character or warband bank out of the
  all-characters totals, charts, tables and ledger. The choice is remembered in the browser.
- Addon: a Pickup category, for gold assigned to it by hand.

### Changed

- Dashboard: laid out like the game's Options window. Reports and characters are in a
  sidebar, the date range is an arrow stepper, totals are shown as Options-style rows, and
  buttons are red. Amounts show coin icons, characters show in their class colors, and the
  tooltip is styled like the game's. It's dark only, like the game, so the light/dark
  toggle is gone.
- Companion: `--summary` prints category names instead of internal keys, in a column wide
  enough for the longest one.
- Companion: the database defaults to `mariposa.db` in the repo root instead of the current
  folder, and every run prints which database it used.
- Companion: `--summary` shows amounts under 1g in silver or copper, and its days start at
  local midnight, matching the dashboard's ranges.
- Dashboard: the footer shows when the game data was saved, next to when the page was built.
- Dashboard: Balance by character starts at each character's first recorded transaction, is
  charted by hour when all history is from today, and is hidden while a single character is
  selected.
- Addon: `/mp chars` shows character names, adding the realm only when two share a name, and
  `/mp week` covers the same calendar days as the dashboard.

### Fixed

- Addon: `/mp log` and debug messages show quest names, like the dashboard, instead of quest
  IDs.
- Addon: net worth no longer reads 0 after logging out. The logout snapshot overwrote the
  warband bank and each character's balance with 0, and the next login then booked the whole
  balance as Untracked Change.
- Companion: resetting a character no longer leaves its old transactions behind, and
  characters deleted from the addon's data are dropped on the next import.
- Addon: opening a bag that holds no gold, or fulfilling a crafting order with no
  commission, no longer labels the next unrelated gold as Reward Bags or Crafting
  Commissions.
- Dashboard: Per day divides by the days your data covers, not the whole selected range.
