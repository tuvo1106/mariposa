#!/usr/bin/env python3
"""Import Mariposa SavedVariables into SQLite for offline dashboards.

The game only writes SavedVariables on logout or /reload, so run this after
either. Imports are idempotent: transactions are keyed by (character, seq).

    python3 mariposa.py                    # auto-detect WoW, write mariposa.db
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
import time
from pathlib import Path

DEFAULT_WTF = [
    Path("/Applications/World of Warcraft/_retail_/WTF"),
    Path(r"C:\Program Files (x86)\World of Warcraft\_retail_\WTF"),
    Path(r"C:\Program Files\World of Warcraft\_retail_\WTF"),
]

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
    char_key TEXT    NOT NULL,
    seq      INTEGER NOT NULL,
    ts       INTEGER NOT NULL,
    amount   INTEGER NOT NULL,  -- copper; negative = spent
    category TEXT    NOT NULL,
    ref      TEXT,
    map_id   INTEGER,
    PRIMARY KEY (char_key, seq)
);
CREATE INDEX IF NOT EXISTS transactions_ts ON transactions (ts);
CREATE TABLE IF NOT EXISTS warband (
    account TEXT PRIMARY KEY,
    gold    INTEGER,
    updated INTEGER
);
"""



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


CATEGORIES_LUA = Path(__file__).resolve().parent.parent / "Mariposa" / "Categories.lua"


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


def import_db(conn: sqlite3.Connection, account: str, data: dict) -> int:
    """Upsert one account's MariposaDB; return the number of new transactions."""
    db = data.get("MariposaDB") or {}
    tx_rows = []
    for char_key, c in (db.get("chars") or {}).items():
        conn.execute(
            """INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(char_key) DO UPDATE SET
                 account=excluded.account, name=excluded.name, realm=excluded.realm,
                 class=excluded.class, faction=excluded.faction, level=excluded.level,
                 gold=excluded.gold, last_seen=excluded.last_seen""",
            (char_key, account, c.get("name"), c.get("realm"), c.get("class"),
             c.get("faction"), c.get("level"), c.get("gold"), c.get("lastSeen")),
        )
        for tx in c.get("tx") or []:
            ref = tx.get("r")
            tx_rows.append((char_key, tx["s"], tx["t"], tx["a"], tx["k"],
                            None if ref is None else str(ref), tx.get("m")))
    after_chars = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)", tx_rows)
    new_tx = conn.total_changes - after_chars

    warband = db.get("warband") or {}
    if "gold" in warband:
        conn.execute(
            """INSERT INTO warband VALUES (?, ?, ?)
               ON CONFLICT(account) DO UPDATE SET gold=excluded.gold, updated=excluded.updated""",
            (account, warband["gold"], warband.get("updated")),
        )
    conn.commit()
    return new_tx


def export_csv(conn: sqlite3.Connection, path: Path):
    rows = conn.execute(
        """SELECT datetime(ts, 'unixepoch', 'localtime'), char_key, category, amount, ref, map_id
           FROM transactions ORDER BY ts, char_key, seq""")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "character", "category", "copper", "ref", "map_id"])
        w.writerows(rows)


def gold(copper: int) -> str:
    return f"{copper / 10000:+,.0f}g"


def print_summary(conn: sqlite3.Connection, days: int):
    since = int(time.time()) - days * 86400
    rows = conn.execute(
        """SELECT category, SUM(amount) FROM transactions WHERE ts >= ?
           GROUP BY category ORDER BY ABS(SUM(amount)) DESC""", (since,)).fetchall()
    print(f"Last {days} days, all characters")
    net = 0
    for category, total in rows:
        note = "  (transfer, not counted)" if category in TRANSFER_CATEGORIES else ""
        if not note:
            net += total
        print(f"  {category:<14} {gold(total):>14}{note}")
    print(f"  {'net':<14} {gold(net):>14}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wtf", type=Path, help="path to _retail_/WTF (auto-detected if omitted)")
    ap.add_argument("--db", type=Path, default=Path("mariposa.db"), help="SQLite output (default: mariposa.db)")
    ap.add_argument("--csv", type=Path, help="also export all transactions to this CSV")
    ap.add_argument("--summary", type=int, metavar="DAYS", help="print totals by category for the last DAYS days")
    ap.add_argument("--dashboard", type=Path, metavar="HTML", help="write an offline HTML dashboard")
    args = ap.parse_args(argv)

    wtf = args.wtf or next((p for p in DEFAULT_WTF if p.is_dir()), None)
    if not wtf or not wtf.is_dir():
        print("Couldn't find your WTF folder; pass --wtf PATH.", file=sys.stderr)
        return 1
    files = find_saved_variables(wtf)
    if not files:
        print(f"No Mariposa.lua under {wtf}/Account/*/SavedVariables. "
              "Log in with the addon enabled, then /reload or log out.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    for account, path in files:
        new_tx = import_db(conn, account, parse_saved_variables(path))
        print(f"{account}: {new_tx} new transactions")
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
