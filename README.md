# Mariposa

A World of Warcraft (retail) addon that keeps an itemized gold ledger across all your
characters, like `+1,000g World Quests · +300g Vendor Sales · −300g AH Purchases`, plus a
companion script that loads the ledger into SQLite for offline dashboards.

See [DESIGN.md](DESIGN.md) for what it tracks and how.

## Stack

- **Lua addon** (`Mariposa/`): the only thing WoW runs. Logs gold changes to SavedVariables.
- **Python 3 companion** (`companion/`): standard library only. Parses SavedVariables into
  SQLite and CSV, because addons can't write files or reach the network.

## Setup

Link the addon into your AddOns folder (macOS shown; on Windows use `mklink /D`):

```bash
ln -s "$PWD/Mariposa" "/Applications/World of Warcraft/_retail_/Interface/AddOns/Mariposa"
lefthook install   # git hooks; see CONTRIBUTING.md
```

In game, `/mp help` lists the commands. After you `/reload` or log out, import the ledger:

```bash
python3 companion/mariposa.py --summary 7          # writes mariposa.db
python3 companion/mariposa.py --csv ledger.csv     # also export CSV
python3 companion/mariposa.py --dashboard dashboard.html   # offline dashboard; open in a browser
```

### Playing on more than one computer

Each computer keeps its own copy of the addon's data. To combine them, copy the other
computer's file into the `imports` folder in this repo, then run the importer as usual:

1. On the other computer, find
   `World of Warcraft/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/Mariposa.lua`.
2. Copy it to `imports/` here, under any name, such as `imports/laptop.lua`. If this
   computer has more than one WoW account, use a subfolder named after the account, such as
   `imports/<ACCOUNT>/laptop.lua`.
3. Run the importer. Copy the file again whenever you want newer data; replacing it is safe.

Use the latest addon on every computer, so each file identifies itself and each login
records enough for gold to be counted once.

To work on the dashboard without playing, generate synthetic data (written to the
gitignored `synthetic/` folder):

```bash
python3 companion/synth.py
python3 companion/mariposa.py --wtf synthetic/WTF --db synthetic/mariposa.db \
  --dashboard synthetic/dashboard.html
```

If the addon shows as out of date, check your client's interface number with
`/dump select(4, GetBuildInfo())` and add it to `## Interface:` in `Mariposa/Mariposa.toc`.

## Testing

```bash
python3 -m unittest discover -s companion/tests
luacheck .                  # optional: brew install luarocks && luarocks install luacheck
```

In game: `/mp debug` prints each transaction as it's recorded. Install BugGrabber + BugSack
to catch Lua errors.

## License

[MIT](LICENSE)
