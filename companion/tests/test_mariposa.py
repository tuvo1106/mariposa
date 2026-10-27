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


class SummaryTest(unittest.TestCase):
    def test_gold_shows_small_amounts_in_silver_and_copper(self):
        self.assertEqual(mariposa.gold(-30), "-30c")
        self.assertEqual(mariposa.gold(2_500), "+25s")
        self.assertEqual(mariposa.gold(0), "0g")
        self.assertEqual(mariposa.gold(12_345_678), "+1,235g")
        self.assertEqual(mariposa.gold(-1_202_000_000), "-120,200g")

    def test_summary_window_starts_at_local_midnight(self):
        from datetime import datetime
        now = datetime(2026, 10, 25, 21, 30)
        self.assertEqual(mariposa.summary_start(1, now), int(datetime(2026, 10, 25).timestamp()))
        self.assertEqual(mariposa.summary_start(7, now), int(datetime(2026, 10, 19).timestamp()))

    def test_default_db_is_in_the_repo_not_the_current_folder(self):
        # Regression: a relative default made each working folder its own database.
        db = mariposa.build_parser().parse_args([]).db
        self.assertTrue(db.is_absolute())
        self.assertEqual(db, Path(mariposa.__file__).resolve().parent.parent / "mariposa.db")


def char_data(txs, *, gold, last_seen, name="Cynze"):
    """A character entry: txs are (seq, ts, amount, category[, prev_seen])."""
    tx = []
    for s, t, a, k, *p in txs:
        entry = {"s": s, "t": t, "a": a, "k": k}
        if p:
            entry["p"] = p[0]
        tx.append(entry)
    return {"name": name, "realm": "Wyrmrest Accord", "class": "WARLOCK", "faction": "Horde",
            "level": 90, "gold": gold, "lastSeen": last_seen,
            "seq": max((s for s, *_ in txs), default=0), "tx": tx}


def install_file(install_id, chars, warband=None):
    db = {"chars": chars}
    if install_id:
        db["installId"] = install_id
    if warband:
        db["warband"] = warband
    return {"MariposaDB": db}


class MultiComputerTest(unittest.TestCase):
    """The same character played on two computers: each keeps its own ledger,
    and a login on one books the other's activity as an adjustment."""

    KEY = "Cynze-WyrmrestAccord"

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        mariposa.init_schema(self.conn)

    def run_import(self, *files):
        listed = set()
        for i, data in enumerate(files):
            _, chars = mariposa.import_file(self.conn, "ACCT", data, mariposa.source_id(data, f"file:{i}"))
            listed |= chars
        mariposa.reconcile(self.conn, listed)

    def ledger(self):
        return self.conn.execute("SELECT category, amount FROM ledger ORDER BY ts").fetchall()

    def desktop(self, adjustment=2000):
        # Played here, then on the laptop, then logged in here again at t=400.
        return install_file("desk", {self.KEY: char_data(
            [(1, 100, 500, "loot"), (2, 400, adjustment, "adjustment", 150)],
            gold=10_500 + adjustment, last_seen=400)})

    def laptop(self):
        return install_file("lap", {self.KEY: char_data(
            [(1, 200, 1200, "quest"), (2, 250, 800, "vendor_sell")], gold=12_500, last_seen=300)})

    def test_adjustment_explained_by_other_computer_is_dropped(self):
        self.run_import(self.desktop(), self.laptop())
        self.assertEqual(self.ledger(), [("loot", 500), ("quest", 1200), ("vendor_sell", 800)])

    def test_partly_explained_adjustment_keeps_the_rest(self):
        # 3000 moved while away, but the laptop only recorded 2000 of it.
        self.run_import(self.desktop(adjustment=3000), self.laptop())
        self.assertIn(("adjustment", 1000), self.ledger())

    def test_import_order_and_repeats_do_not_matter(self):
        self.run_import(self.laptop(), self.desktop())
        self.run_import(self.desktop(), self.laptop())
        self.assertEqual(len(self.ledger()), 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 4)

    def test_same_seq_on_two_computers_is_not_a_reset(self):
        self.run_import(self.desktop(), self.laptop())
        self.run_import(self.desktop())
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE source = 'lap'").fetchone()[0], 2)

    def test_balance_comes_from_the_computer_that_saw_it_last(self):
        self.run_import(self.desktop(), self.laptop())
        self.assertEqual(self.conn.execute("SELECT gold FROM characters").fetchone()[0], 12_500)

    def test_newest_warband_snapshot_wins(self):
        old = install_file("lap", {}, {"gold": 1, "updated": 100})
        new = install_file("desk", {}, {"gold": 2, "updated": 200})
        self.run_import(new, old)
        self.assertEqual(self.conn.execute("SELECT gold FROM warband").fetchone()[0], 2)

    def test_adjustment_without_prev_seen_is_clamped(self):
        # Older addon versions don't record when the character was last seen.
        desk = install_file("desk", {self.KEY: char_data(
            [(1, 100, 500, "loot"), (2, 400, 1500, "adjustment")], gold=12_000, last_seen=400)})
        self.run_import(desk, self.laptop())
        # The laptop's 2000 covers more than the 1500 adjustment; it's capped, not flipped.
        self.assertNotIn("adjustment", [k for k, _ in self.ledger()])

    def test_v0_database_is_migrated_without_duplicates(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE transactions (char_key TEXT NOT NULL, seq INTEGER NOT NULL, ts INTEGER NOT NULL,
                amount INTEGER NOT NULL, category TEXT NOT NULL, ref TEXT, map_id INTEGER,
                PRIMARY KEY (char_key, seq));
            INSERT INTO transactions VALUES ('Cynze-WyrmrestAccord', 1, 100, 500, 'loot', NULL, NULL);
        """)
        mariposa.init_schema(conn)
        self.assertEqual(conn.execute("SELECT source FROM transactions").fetchall(), [("",)])
        self.conn = conn
        self.run_import(self.desktop())
        self.assertEqual(conn.execute(
            "SELECT source, COUNT(*) FROM transactions GROUP BY source").fetchall(), [("desk", 2)])


class QuestNamesTest(unittest.TestCase):
    KEY = "Cynze-WyrmrestAccord"

    def details(self, names):
        conn = sqlite3.connect(":memory:")
        mariposa.init_schema(conn)
        data = install_file("desk", {self.KEY: char_data(
            [(1, 10, 500, "world_quest"), (2, 20, 300, "quest"), (3, 30, 100, "vendor_sell")],
            gold=900, last_seen=30)})
        for t, ref in zip(data["MariposaDB"]["chars"][self.KEY]["tx"], (94574, 88992, 94574)):
            t["r"] = ref
        data["MariposaDB"]["questNames"] = names
        mariposa.import_db(conn, "ACCT", data)
        return [r[0] for r in conn.execute("SELECT ref FROM ledger ORDER BY ts")]

    def test_quest_rewards_show_their_title(self):
        # The vendor sale's detail happens to match a quest ID; only quest rewards are renamed.
        self.assertEqual(self.details({94574: "Supply the Front"}), ["Supply the Front", "88992", "94574"])

    def test_unnamed_quest_keeps_its_id(self):
        self.assertEqual(self.details({}), ["94574", "88992", "94574"])

    def test_names_keyed_one_to_n_parse_as_a_list(self):
        conn = sqlite3.connect(":memory:")
        mariposa.init_schema(conn)
        data = install_file("desk", {})
        data["MariposaDB"]["questNames"] = ["First", "Second"]  # what the parser gives for [1], [2]
        mariposa.import_db(conn, "ACCT", data)
        self.assertEqual(sorted(conn.execute("SELECT id, name FROM quest_names")),
                         [("1", "First"), ("2", "Second")])


class GroupTest(unittest.TestCase):
    def test_commission_profession_reaches_the_ledger(self):
        conn = sqlite3.connect(":memory:")
        mariposa.init_schema(conn)
        data = install_file("desk", {"Cynze-WyrmrestAccord": char_data(
            [(1, 10, 600, "crafting_commission"), (2, 20, 300, "crafting_commission")],
            gold=900, last_seen=20)})
        data["MariposaDB"]["chars"]["Cynze-WyrmrestAccord"]["tx"][0]["g"] = "Blacksmithing"
        mariposa.import_db(conn, "ACCT", data)
        self.assertEqual(conn.execute("SELECT grp, amount FROM ledger ORDER BY ts").fetchall(),
                         [("Blacksmithing", 600), (None, 300)])

    def test_v1_database_gains_the_group_column(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE transactions (char_key TEXT NOT NULL, source TEXT NOT NULL, seq INTEGER NOT NULL,
                ts INTEGER NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL, ref TEXT, map_id INTEGER,
                prev_seen INTEGER, explained INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (char_key, source, seq));
            CREATE VIEW ledger AS SELECT * FROM transactions;
            INSERT INTO transactions (char_key, source, seq, ts, amount, category)
                VALUES ('Cynze-WyrmrestAccord', 'desk', 1, 10, 500, 'loot');
            PRAGMA user_version = 1;
        """)
        mariposa.init_schema(conn)
        self.assertEqual(conn.execute("SELECT amount, grp FROM ledger").fetchall(), [(500, None)])
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], mariposa.SCHEMA_VERSION)


class FindImportsTest(unittest.TestCase):
    def test_accounts_from_subfolders_or_the_single_local_account(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "OTHER").mkdir()
            (root / "laptop.lua").write_text("MariposaDB = {}")
            (root / "OTHER" / "x.lua").write_text("MariposaDB = {}")
            found = {(a, p.name) for a, p in mariposa.find_imports(root, ["MAIN"])}
            self.assertEqual(found, {("MAIN", "laptop.lua"), ("OTHER", "x.lua")})
            # With two local accounts, a loose file is ambiguous and skipped.
            loose = [p.name for _, p in mariposa.find_imports(root, ["A", "B"])]
            self.assertEqual(loose, ["x.lua"])

    def test_missing_folder_is_empty(self):
        self.assertEqual(mariposa.find_imports(Path("does-not-exist"), ["MAIN"]), [])


class MainImportsTest(unittest.TestCase):
    """main() reads the local WTF plus an imports folder, but an explicit --wtf
    alone must not pick up the default imports folder."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        sv = root / "WTF" / "Account" / "MAIN" / "SavedVariables"
        sv.mkdir(parents=True)
        (sv / "Mariposa.lua").write_text(
            'MariposaDB = { ["installId"] = "desk", ["chars"] = { ["Here-Realm"] = '
            '{ ["name"] = "Here", ["gold"] = 1, ["lastSeen"] = 1, ["seq"] = 0, ["tx"] = {} } } }')
        self.imports = root / "imports"
        self.imports.mkdir()
        (self.imports / "laptop.lua").write_text(
            'MariposaDB = { ["installId"] = "lap", ["chars"] = { ["There-Realm"] = '
            '{ ["name"] = "There", ["gold"] = 2, ["lastSeen"] = 2, ["seq"] = 0, ["tx"] = {} } } }')
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, db):
        from contextlib import closing
        with closing(sqlite3.connect(db)) as conn:
            return {r[0] for r in conn.execute("SELECT name FROM characters")}

    def test_imports_folder_is_merged(self):
        db = self.root / "a.db"
        mariposa.main(["--wtf", str(self.root / "WTF"), "--imports", str(self.imports), "--db", str(db)])
        self.assertEqual(self.names(db), {"Here", "There"})

    def test_explicit_wtf_ignores_default_imports(self):
        db = self.root / "b.db"
        saved = mariposa.IMPORTS
        mariposa.IMPORTS = self.imports
        try:
            mariposa.main(["--wtf", str(self.root / "WTF"), "--db", str(db)])
        finally:
            mariposa.IMPORTS = saved
        self.assertEqual(self.names(db), {"Here"})


if __name__ == "__main__":
    unittest.main()
