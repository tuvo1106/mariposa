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


if __name__ == "__main__":
    unittest.main()
