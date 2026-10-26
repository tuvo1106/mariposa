import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mariposa  # noqa: E402

FIXTURE_WTF = Path(__file__).parent / "fixtures" / "WTF"


class LuaParserTest(unittest.TestCase):
    def parse(self, text):
        return mariposa.LuaParser(text).parse()

    def test_scalars(self):
        self.assertEqual(
            self.parse('A = { ["n"] = -12, ["f"] = 1.5, ["b"] = true, ["z"] = nil, x = "hi" }'),
            {"A": {"n": -12, "f": 1.5, "b": True, "z": None, "x": "hi"}},
        )

    def test_arrays_and_comments(self):
        self.assertEqual(self.parse("A = { 1, -- [1]\n 2, -- [2]\n}"), {"A": [1, 2]})

    def test_empty_table_is_dict(self):
        self.assertEqual(self.parse("A = {}"), {"A": {}})

    def test_string_escapes(self):
        self.assertEqual(self.parse(r'A = "a\"b\\c\nd\065"'), {"A": 'a"b\\c\ndA'})

    def test_utf8(self):
        text = 'A = "Ålt"'.encode("utf-8").decode("latin-1")
        self.assertEqual(self.parse(text), {"A": "Ålt"})

    def test_error_reports_line(self):
        with self.assertRaisesRegex(mariposa.LuaParseError, "line 2"):
            self.parse("A = {\n @ }")


class CategoriesTest(unittest.TestCase):
    def test_read_from_addon(self):
        self.assertEqual(mariposa.CATEGORIES["world_quest"]["label"], "World Quests")
        self.assertEqual(mariposa.TRANSFER_CATEGORIES, {"xfer_warband", "xfer_mail"})


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(mariposa.SCHEMA)
        [(self.account, self.path)] = mariposa.find_saved_variables(FIXTURE_WTF)

    def import_fixture(self):
        return mariposa.import_db(self.conn, self.account, mariposa.parse_saved_variables(self.path))

    def test_import_is_idempotent(self):
        self.assertEqual(self.import_fixture(), 3)
        self.assertEqual(self.import_fixture(), 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 3)

    def test_rows(self):
        self.import_fixture()
        self.assertEqual(
            self.conn.execute("SELECT name, gold FROM characters ORDER BY gold").fetchall(),
            [("Ålt", 42), ("Tuvo", 123456789)],
        )
        self.assertEqual(
            self.conn.execute("SELECT ref FROM transactions WHERE seq = 2").fetchone()[0],
            'Mycobloom "x200"',
        )
        self.assertEqual(
            self.conn.execute("SELECT account, gold FROM warband").fetchone(),
            ("TESTACCOUNT", 1500000000),
        )


class ResetAwareImportTest(unittest.TestCase):
    """A character whose in-game ledger is reset reuses seq numbers; the import
    must replace the stale rows rather than keep them (INSERT OR IGNORE would)."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(mariposa.SCHEMA)

    def data(self, txs, *, seq=None, gold=100):
        # txs: list of (s, t, a, k). seq defaults to the highest s present.
        tx = [{"s": s, "t": t, "a": a, "k": k} for (s, t, a, k) in txs]
        counter = seq if seq is not None else max((s for s, *_ in txs), default=0)
        return {"MariposaDB": {"chars": {"Cynze-WyrmrestAccord": {
            "name": "Cynze", "realm": "Wyrmrest Accord", "class": "WARLOCK",
            "faction": "Horde", "level": 90, "gold": gold, "lastSeen": 100, "seq": counter,
            "tx": tx}}}}

    def kinds(self):
        return [r[0] for r in self.conn.execute(
            "SELECT category FROM transactions ORDER BY seq")]

    def imp(self, data):
        return mariposa.import_db(self.conn, "ACCT", data)

    def test_append_keeps_history(self):
        self.assertEqual(self.imp(self.data([(1, 10, 5, "loot"), (2, 20, 5, "loot")])), 2)
        # Same two plus a new third: only the new one counts, nothing is replaced.
        self.assertEqual(self.imp(self.data(
            [(1, 10, 5, "loot"), (2, 20, 5, "loot"), (3, 30, 5, "quest")])), 1)
        self.assertEqual(self.kinds(), ["loot", "loot", "quest"])

    def test_reset_shorter_ledger_replaces(self):
        self.imp(self.data([(1, 10, 5, "loot"), (2, 20, 5, "loot"), (3, 30, 5, "loot")]))
        # Deleted and recreated: counter restarts, seqs reused for new transactions.
        self.assertEqual(self.imp(self.data([(1, 40, 9, "vendor_sell")])), 1)
        self.assertEqual(self.kinds(), ["vendor_sell"])

    def test_reset_to_empty_ledger_purges(self):
        self.imp(self.data([(1, 10, 5, "loot"), (2, 20, 5, "loot")]))
        # Recreated but no transactions yet (tx = {}, seq = 0): stale rows must go.
        self.assertEqual(self.imp(self.data([], seq=0)), 0)
        self.assertEqual(self.kinds(), [])

    def test_reset_same_length_different_content(self):
        self.imp(self.data([(1, 10, 5, "loot"), (2, 20, 5, "loot")]))
        # Counter didn't drop, but overlapping seqs now hold different transactions.
        self.assertEqual(self.imp(self.data([(1, 40, 9, "quest"), (2, 50, 9, "quest")])), 2)
        self.assertEqual(self.kinds(), ["quest", "quest"])

    def two_chars(self):
        def char(name, t, k):
            return {"name": name, "realm": "Wyrmrest Accord", "class": "MAGE",
                    "faction": "Horde", "level": 90, "gold": 1, "lastSeen": 1, "seq": 1,
                    "tx": [{"s": 1, "t": t, "a": 5, "k": k}]}
        return {"MariposaDB": {"chars": {
            "A-WyrmrestAccord": char("A", 10, "loot"),
            "B-WyrmrestAccord": char("B", 11, "quest")}}}

    def names(self):
        return {r[0] for r in self.conn.execute("SELECT name FROM characters")}

    def test_deleted_character_is_pruned(self):
        self.imp(self.two_chars())
        self.assertEqual(self.names(), {"A", "B"})
        one = self.two_chars()
        del one["MariposaDB"]["chars"]["B-WyrmrestAccord"]  # B deleted in game
        self.imp(one)
        self.assertEqual(self.names(), {"A"})
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE char_key = 'B-WyrmrestAccord'").fetchone()[0], 0)

    def test_empty_chars_does_not_wipe(self):
        self.imp(self.data([(1, 10, 5, "loot")]))
        # A file with no characters (truncated or mid-write) must not prune.
        self.imp({"MariposaDB": {"chars": {}}})
        self.assertEqual(self.names(), {"Cynze"})


if __name__ == "__main__":
    unittest.main()
