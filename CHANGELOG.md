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

### Changed

- Dashboard: styled after the WoW interface, with bronze-framed panels, red panel buttons,
  gold titles, coin icons, class-colored character names, and a game-style tooltip. It's
  dark only, like the game, so the light/dark toggle is gone.

### Fixed
