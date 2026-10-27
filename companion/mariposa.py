#!/usr/bin/env python3
"""Import Mariposa SavedVariables into SQLite for offline dashboards.

The game only writes SavedVariables on logout or /reload, so run this after
either. Imports are idempotent: transactions are keyed by (character, source,
seq), where source is the install that recorded them. A character whose
in-game ledger was reset (deleted and recreated, so its seq counter restarts)
is detected and its stale rows are replaced.

Playing on several computers: copy each other computer's Mariposa.lua into
imports/ (see find_imports). Their ledgers are merged, and login adjustments
that another computer's ledger explains are dropped (see reconcile).

    python3 mariposa.py                    # auto-detect WoW, write <repo>/mariposa.db
    python3 mariposa.py --wtf PATH --db out.db --csv out.csv
    python3 mariposa.py --summary 7        # print last 7 days by category
    python3 mariposa.py --dashboard dashboard.html
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

# The repo root. Defaults hang off it rather than the current folder, so the
# importer finds the same database no matter where it's run from.
REPO = Path(__file__).resolve().parent.parent
IMPORTS = REPO / "imports"

DEFAULT_WTF = [
    Path("/Applications/World of Warcraft/_retail_/WTF"),
    Path(r"C:\Program Files (x86)\World of Warcraft\_retail_\WTF"),
    Path(r"C:\Program Files\World of Warcraft\_retail_\WTF"),
]

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    char_key  TEXT PRIMARY KEY,
    account   TEXT,
    name      TEXT,
    realm     TEXT,
    class     TEXT,
    faction   TEXT,
    level     INTEGER,
    gold      INTEGER,
    last_seen INTEGER
);
CREATE TABLE IF NOT EXISTS transactions (
    char_key  TEXT    NOT NULL,
    source    TEXT    NOT NULL,  -- the install that recorded it ('' = before sources existed)
    seq       INTEGER NOT NULL,
    ts        INTEGER NOT NULL,
    amount    INTEGER NOT NULL,  -- copper; negative = spent
    category  TEXT    NOT NULL,
    ref       TEXT,
    map_id    INTEGER,
    prev_seen INTEGER,           -- adjustments: when this install last saw the character
    grp       TEXT,              -- a group within the category, e.g. a commission's profession
    explained INTEGER NOT NULL DEFAULT 0,  -- adjustments: part another install's ledger shows
    PRIMARY KEY (char_key, source, seq)
);
CREATE INDEX IF NOT EXISTS transactions_ts ON transactions (ts);
CREATE TABLE IF NOT EXISTS warband (
    account TEXT PRIMARY KEY,
    gold    INTEGER,
    updated INTEGER
);
-- Quest titles the addon looked up (MariposaDB.questNames), merged from every file.
CREATE TABLE IF NOT EXISTS quest_names (
    id   TEXT PRIMARY KEY,  -- the quest ID as stored in transactions.ref
    name TEXT NOT NULL
);
-- What every report reads: adjustments net of what other installs explain,
-- dropping those that are fully explained, and quest rewards showing the
-- quest's title instead of its ID once it's known. Recreated on every run, so
-- an older database picks up changes to it.
DROP VIEW IF EXISTS ledger;
CREATE VIEW ledger AS
    SELECT t.char_key, t.source, t.seq, t.ts, t.amount - t.explained AS amount, t.category,
           COALESCE(q.name, t.ref) AS ref, t.map_id, t.grp
    FROM transactions t
    LEFT JOIN quest_names q
      ON t.category IN ('quest', 'world_quest', 'bonus') AND q.id = t.ref
    WHERE t.amount - t.explained != 0;
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the schema, migrating an older database in place: it's the
    durable history (ADR 0003), so it's never rebuilt."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_tx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transactions'").fetchone()
    if has_tx and version < 1:
        # v0 keyed transactions by (char_key, seq) alone. Keep every row under a
        # blank source; the next import of the file they came from claims them,
        # since an identical transaction is the same one wherever it's filed.
        conn.executescript("""
            DROP INDEX IF EXISTS transactions_ts;
            ALTER TABLE transactions RENAME TO transactions_v0;
        """)
        conn.executescript(SCHEMA)
        conn.execute("""INSERT INTO transactions (char_key, source, seq, ts, amount, category, ref, map_id)
                        SELECT char_key, '', seq, ts, amount, category, ref, map_id FROM transactions_v0""")
        conn.execute("DROP TABLE transactions_v0")
    elif has_tx and version < 2:
        # v1 -> v2: transactions gain grp. The view is recreated below.
        conn.executescript("""
            DROP VIEW IF EXISTS ledger;
            ALTER TABLE transactions ADD COLUMN grp TEXT;
        """)
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


class LuaParseError(ValueError):
    pass


class LuaParser:
    """Parses the subset of Lua that WoW writes to SavedVariables:
    top-level `Name = value` assignments of tables, strings, numbers,
    booleans and nil.

    Text is decoded as latin-1 so each char is one byte; strings are
    re-decoded as UTF-8 once their escapes are resolved.
    """

    _NUMBER = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
    _IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    _ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
                "f": "\f", "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}

    def __init__(self, text: str):
        self.s = text
        self.i = 0

    def parse(self) -> dict:
        result = {}
        while True:
            self._ws()
            if self.i >= len(self.s):
                return result
            name = self._ident()
            self._ws()
            self._expect("=")
            result[name] = self._value()

    def _error(self, msg: str):
        line = self.s.count("\n", 0, self.i) + 1
        raise LuaParseError(f"{msg} at line {line}")

    def _ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c.isspace():
                self.i += 1
            elif s.startswith("--[[", self.i):
                end = s.find("]]", self.i)
                self.i = len(s) if end < 0 else end + 2
            elif s.startswith("--", self.i):
                end = s.find("\n", self.i)
                self.i = len(s) if end < 0 else end + 1
            else:
                return

    def _expect(self, token: str):
        if not self.s.startswith(token, self.i):
            self._error(f"expected {token!r}")
        self.i += len(token)

    def _ident(self) -> str:
        m = self._IDENT.match(self.s, self.i)
        if not m:
            self._error("expected identifier")
        self.i = m.end()
        return m.group()

    def _value(self):
        self._ws()
        s, i = self.s, self.i
        c = s[i] if i < len(s) else ""
        if c == "{":
            return self._table()
        if c in "\"'":
            return self._string()
        for word, val in (("true", True), ("false", False), ("nil", None)):
            if s.startswith(word, i) and not (s[i + len(word):i + len(word) + 1].isalnum()):
                self.i += len(word)
                return val
        m = self._NUMBER.match(s, i)
        if m:
            self.i = m.end()
            text = m.group()
            if "x" in text.lower():
                return int(text, 16)
            if any(ch in text for ch in ".eE"):
                return float(text)
            return int(text)
        self._error(f"unexpected {c!r}")

    def _string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        out = []
        s = self.s
        while True:
            if self.i >= len(s):
                self._error("unterminated string")
            c = s[self.i]
            if c == quote:
                self.i += 1
                break
            if c == "\\":
                nxt = s[self.i + 1]
                if nxt.isdigit():
                    m = re.match(r"\d{1,3}", s[self.i + 1:])
                    out.append(chr(int(m.group())))
                    self.i += 1 + len(m.group())
                    continue
                out.append(self._ESCAPES.get(nxt, nxt))
                self.i += 2
                continue
            out.append(c)
            self.i += 1
        return "".join(out).encode("latin-1").decode("utf-8", errors="replace")

    def _table(self):
        self._expect("{")
        items: dict = {}
        next_index = 1
        while True:
            self._ws()
            if self.s.startswith("}", self.i):
                self.i += 1
                break
            if self.s.startswith("[", self.i):
                self.i += 1
                key = self._value()
                self._ws()
                self._expect("]")
                self._ws()
                self._expect("=")
                items[key] = self._value()
            else:
                m = self._IDENT.match(self.s, self.i)
                after = m and self.s[m.end():].lstrip()
                if m and after.startswith("=") and not after.startswith("=="):
                    self.i = m.end()
                    self._ws()
                    self._expect("=")
                    items[m.group()] = self._value()
                else:
                    items[next_index] = self._value()
                    next_index += 1
            self._ws()
            if self.i < len(self.s) and self.s[self.i] in ",;":
                self.i += 1
        # A table keyed exactly 1..n is a Lua array.
        if items and all(isinstance(k, int) for k in items) and sorted(items) == list(range(1, len(items) + 1)):
            return [items[k] for k in range(1, len(items) + 1)]
        return items


CATEGORIES_LUA = REPO / "Mariposa" / "Categories.lua"


def load_categories(path: Path = CATEGORIES_LUA) -> dict:
    """Read `ns.Categories` from the addon, so it stays the one place categories
    are defined: {key: {"label": ..., "transfer": True?}}."""
    text = path.read_text(encoding="latin-1")
    parser = LuaParser(text)
    parser.i = text.index("{", text.index("ns.Categories ="))
    return parser._value()


CATEGORIES = load_categories()
TRANSFER_CATEGORIES = {k for k, v in CATEGORIES.items() if v.get("transfer")}


def parse_saved_variables(path: Path) -> dict:
    return LuaParser(path.read_text(encoding="latin-1")).parse()


def find_saved_variables(wtf: Path) -> list[tuple[str, Path]]:
    """(account folder name, Mariposa.lua) for every WoW account under WTF."""
    return [(p.parent.parent.name, p)
            for p in sorted(wtf.glob("Account/*/SavedVariables/Mariposa.lua"))]


def find_imports(folder: Path, local_accounts: list[str]) -> list[tuple[str, Path]]:
    """(account, file) for Mariposa.lua files copied from other computers.

    A file inside a subfolder belongs to the account the subfolder is named
    after (imports/PHOSHIZZZ0/laptop.lua). A file directly in imports/ belongs
    to the one local account; with several local accounts it must go in a
    subfolder, since a SavedVariables file doesn't name its account."""
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.rglob("*.lua")):
        rel = path.relative_to(folder)
        if len(rel.parts) > 1:
            found.append((rel.parts[0], path))
        elif len(local_accounts) == 1:
            found.append((local_accounts[0], path))
        else:
            print(f"skipping {path}: put it in a subfolder named after its WoW account "
                  f"({', '.join(local_accounts) or 'none found locally'})", file=sys.stderr)
    return found


def source_id(data: dict, fallback: str) -> str:
    """The install that wrote this file. Files from addon versions before
    installId existed fall back to where they were read from."""
    install = (data.get("MariposaDB") or {}).get("installId")
    return str(install) if install else fallback


def import_file(conn: sqlite3.Connection, account: str, data: dict, source: str) -> tuple[int, set[str]]:
    """Upsert one file's ledgers under `source`. Returns (new transactions,
    characters the file lists). Call reconcile() after the last file."""
    db = data.get("MariposaDB") or {}
    chars = db.get("chars") or {}
    new_tx = 0
    for char_key, c in chars.items():
        # One row per character: keep whichever install saw it most recently.
        conn.execute(
            """INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(char_key) DO UPDATE SET
                 account=excluded.account, name=excluded.name, realm=excluded.realm,
                 class=excluded.class, faction=excluded.faction, level=excluded.level,
                 gold=excluded.gold, last_seen=excluded.last_seen
               WHERE COALESCE(excluded.last_seen, 0) >= COALESCE(characters.last_seen, 0)""",
            (char_key, account, c.get("name"), c.get("realm"), c.get("class"),
             c.get("faction"), c.get("level"), c.get("gold"), c.get("lastSeen")),
        )
        incoming = []
        for tx in c.get("tx") or []:
            ref = tx.get("r")
            incoming.append((char_key, source, tx["s"], tx["t"], tx["a"], tx["k"],
                             None if ref is None else str(ref), tx.get("m"), tx.get("p"), tx.get("g")))

        # The same transaction filed under another source is this one: a file
        # imported before its install had an ID, or under another name. Claim it.
        claimed = 0
        for r in incoming:
            claimed += conn.execute(
                """DELETE FROM transactions WHERE char_key = ? AND source != ?
                   AND seq = ? AND ts = ? AND amount = ? AND category = ?""",
                (char_key, source, r[2], r[3], r[4], r[5])).rowcount

        # The in-game ledger is append-only, so stored rows must still be present
        # with identical content. Two things prove a reset (the character was
        # deleted and recreated, restarting its seq counter): the live seq
        # counter dropped below a seq we've stored, or an overlapping seq now
        # holds a different transaction. Either way the stored rows are stale, so
        # replace this source's ledger for the character wholesale. (Pruning low
        # seqs wouldn't trip this: the counter climbs and overlaps match.)
        stored = {row[0]: (row[1], row[2], row[3]) for row in conn.execute(
            "SELECT seq, ts, amount, category FROM transactions WHERE char_key = ? AND source = ?",
            (char_key, source))}
        counter = c.get("seq") or 0
        reset = (bool(stored) and counter < max(stored)) or any(
            r[2] in stored and stored[r[2]] != (r[3], r[4], r[5]) for r in incoming)

        insert = """INSERT {} INTO transactions
                    (char_key, source, seq, ts, amount, category, ref, map_id, prev_seen, grp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        before = conn.total_changes
        if reset:
            conn.execute("DELETE FROM transactions WHERE char_key = ? AND source = ?", (char_key, source))
            before = conn.total_changes
            conn.executemany(insert.format(""), incoming)
        else:
            conn.executemany(insert.format("OR IGNORE"), incoming)
        new_tx += conn.total_changes - before - claimed

    # Characters this file no longer lists were deleted on that install; drop
    # that install's ledgers for them. Skipped for a file that lists none, so a
    # truncated read can't wipe anything.
    if chars:
        placeholders = ",".join("?" * len(chars))
        conn.execute(f"DELETE FROM transactions WHERE source = ? AND char_key NOT IN ({placeholders})",
                     (source, *chars))

    # One warband bank per account: keep the most recent snapshot.
    # Quest titles are the same for every character and computer; any file's will do.
    names = db.get("questNames") or {}
    if isinstance(names, list):  # the parser turns keys 1..n into a list
        names = dict(enumerate(names, start=1))
    conn.executemany("INSERT OR REPLACE INTO quest_names VALUES (?, ?)",
                     [(str(qid), str(name)) for qid, name in names.items()])

    warband = db.get("warband") or {}
    if "gold" in warband:
        conn.execute(
            """INSERT INTO warband VALUES (?, ?, ?)
               ON CONFLICT(account) DO UPDATE SET gold=excluded.gold, updated=excluded.updated
               WHERE COALESCE(excluded.updated, 0) >= COALESCE(warband.updated, 0)""",
            (account, warband["gold"], warband.get("updated")),
        )
    return new_tx, set(chars)


def reconcile(conn: sqlite3.Connection, listed: set[str]) -> None:
    """Finish an import run across every file read in it.

    - Drops characters no file lists that have no transactions left.
    - Works out how much of each login adjustment another install explains.
      Playing a character on another computer moves its gold; the next login
      here books the difference as an adjustment, while the other computer
      recorded the same money in detail. So an adjustment is net of every
      other install's transactions for that character in the gap it covers:
      after this install last saw the character, up to the login."""
    if listed:
        placeholders = ",".join("?" * len(listed))
        conn.execute(
            f"""DELETE FROM characters WHERE char_key NOT IN ({placeholders})
                AND char_key NOT IN (SELECT char_key FROM transactions)""", tuple(listed))

    conn.execute("UPDATE transactions SET explained = 0")
    adjustments = conn.execute(
        """SELECT char_key, source, seq, ts, amount, prev_seen FROM transactions
           WHERE category = 'adjustment'""").fetchall()
    for key, src, seq, ts, amount, prev in adjustments:
        exact = prev is not None
        if not exact:
            # Older files don't record it: start after this install's previous
            # transaction for the character, which may be early, hence the clamp below.
            prev = conn.execute(
                "SELECT MAX(ts) FROM transactions WHERE char_key = ? AND source = ? AND ts < ?",
                (key, src, ts)).fetchone()[0] or 0
        other = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM transactions
               WHERE char_key = ? AND source NOT IN (?, '') AND category != 'adjustment'
                 AND ts > ? AND ts <= ?""", (key, src, prev, ts)).fetchone()[0]
        if not exact:
            other = max(0, min(other, amount)) if amount > 0 else min(0, max(other, amount))
        if other:
            conn.execute("UPDATE transactions SET explained = ? WHERE char_key = ? AND source = ? AND seq = ?",
                         (other, key, src, seq))
    conn.commit()


def import_db(conn: sqlite3.Connection, account: str, data: dict, source: str | None = None) -> int:
    """Import a single file and reconcile; returns the number of new transactions."""
    new_tx, listed = import_file(conn, account, data, source or source_id(data, f"wtf:{account}"))
    reconcile(conn, listed)
    return new_tx


def export_csv(conn: sqlite3.Connection, path: Path):
    rows = conn.execute(
        """SELECT datetime(ts, 'unixepoch', 'localtime'), char_key, category, amount, ref, map_id, source, grp
           FROM ledger ORDER BY ts, char_key, source, seq""")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "character", "category", "copper", "ref", "map_id", "source", "group"])
        w.writerows(rows)


def gold(copper: int) -> str:
    """Signed whole gold, or silver/copper below 1g so postage doesn't read 0g.
    Same rule as the dashboard's coinParts()."""
    n = abs(round(copper))
    sign = "" if n == 0 else ("-" if copper < 0 else "+")
    if 0 < n < 10000:
        return f"{sign}{n // 100}s" if n >= 100 else f"{sign}{n}c"
    return f"{sign}{round(n / 10000):,}g"


def summary_start(days: int, now: datetime | None = None) -> int:
    """Local midnight `days - 1` days ago: the same calendar-day window the
    dashboard's ranges use, so both report the same totals."""
    midnight = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight - timedelta(days=days - 1)).timestamp())


def print_summary(conn: sqlite3.Connection, days: int):
    since = summary_start(days)
    rows = conn.execute(
        """SELECT category, SUM(amount) FROM ledger WHERE ts >= ?
           GROUP BY category ORDER BY ABS(SUM(amount)) DESC""", (since,)).fetchall()
    print(("Today" if days == 1 else f"Last {days} days") + ", all characters")
    # Readable labels, in a column wide enough for the longest one, so a long
    # name like "Crafting Commissions" can't push its amount out of line.
    labels = [CATEGORIES.get(c, {}).get("label", c) for c, _ in rows]
    width = max([len(s) for s in labels] + [len("Net")])
    net = 0
    for (category, total), label in zip(rows, labels):
        note = "  (transfer, not counted)" if category in TRANSFER_CATEGORIES else ""
        if not note:
            net += total
        print(f"  {label:<{width}} {gold(total):>14}{note}")
    print(f"  {'Net':<{width}} {gold(net):>14}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wtf", type=Path, help="path to _retail_/WTF (auto-detected if omitted)")
    ap.add_argument("--db", type=Path, default=REPO / "mariposa.db",
                    help="SQLite output (default: mariposa.db in the repo root)")
    ap.add_argument("--imports", type=Path,
                    help="folder of Mariposa.lua files copied from other computers "
                         "(default: imports in the repo root, unless --wtf is given)")
    ap.add_argument("--csv", type=Path, help="also export all transactions to this CSV")
    ap.add_argument("--summary", type=int, metavar="DAYS", help="print totals by category for the last DAYS days")
    ap.add_argument("--dashboard", type=Path, metavar="HTML", help="write an offline HTML dashboard")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    wtf = args.wtf or next((p for p in DEFAULT_WTF if p.is_dir()), None)
    local = find_saved_variables(wtf) if wtf and wtf.is_dir() else []
    # An explicit --wtf (synthetic data, say) reads only what it's pointed at,
    # so the default imports folder doesn't leak real data into it.
    imports = args.imports or (None if args.wtf else IMPORTS)
    imported = find_imports(imports, [account for account, _ in local]) if imports else []
    if not local and not imported:
        where = f"{wtf}/Account/*/SavedVariables" if wtf and wtf.is_dir() else "a WTF folder (pass --wtf PATH)"
        print(f"No Mariposa.lua under {where}" + (f", and none in {imports}" if imports else "") + ". "
              "Log in with the addon enabled, then /reload or log out.", file=sys.stderr)
        return 1

    print(f"database: {args.db.resolve()}")
    inputs = [(account, path, f"wtf:{account}", "this computer") for account, path in local]
    inputs += [(account, path, f"file:{path.relative_to(imports).as_posix()}",
                f"imports/{path.relative_to(imports).as_posix()}") for account, path in imported]
    # Closed explicitly: on Windows an open connection keeps the file locked.
    with closing(sqlite3.connect(args.db)) as conn:
        init_schema(conn)
        listed: set[str] = set()
        for account, path, fallback, label in inputs:
            data = parse_saved_variables(path)
            new_tx, chars = import_file(conn, account, data, source_id(data, fallback))
            listed |= chars
            print(f"{label} ({account}): {new_tx} new transactions")
        reconcile(conn, listed)
        if args.csv:
            export_csv(conn, args.csv)
            print(f"wrote {args.csv}")
        if args.summary:
            print_summary(conn, args.summary)
        if args.dashboard:
            from dashboard import render_dashboard
            render_dashboard(conn, args.dashboard, CATEGORIES)
            print(f"wrote {args.dashboard}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
