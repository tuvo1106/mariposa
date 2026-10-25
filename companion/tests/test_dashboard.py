import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard  # noqa: E402
import mariposa  # noqa: E402
import synth  # noqa: E402

END = 1_761_400_000  # fixed so the synthetic data is reproducible


class SyntheticPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        wtf = Path(cls.tmp.name) / "WTF"
        cls.db = synth.generate(days=60, seed=3, end=END)
        synth.write_wtf(wtf, cls.db)
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript(mariposa.SCHEMA)
        [(account, path)] = mariposa.find_saved_variables(wtf)
        cls.imported = mariposa.import_db(cls.conn, account, mariposa.parse_saved_variables(path))
        cls.data = dashboard.dashboard_data(cls.conn, mariposa.CATEGORIES)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_round_trips_through_lua(self):
        self.assertEqual(self.imported, sum(len(c["tx"]) for c in self.db["chars"].values()))

    def test_balances_never_go_negative(self):
        for key, c in self.db["chars"].items():
            balance = c["gold"] - sum(tx["a"] for tx in c["tx"])
            for tx in c["tx"]:
                balance += tx["a"]
                self.assertGreaterEqual(balance, 0, key)

    def test_warband_mirror_nets_transfers_to_zero(self):
        transfers = set(self.data["transfers"])
        net = sum(t[2] for t in self.data["tx"] if t[3] in transfers)
        self.assertEqual(net, 0)
        self.assertEqual(self.data["pockets"][-1]["kind"], "warband")

    def test_net_worth_history_reconstructs_start(self):
        pockets = self.data["pockets"]
        start = sum(p["gold"] for p in pockets) - sum(t[2] for t in self.data["tx"])
        expected = sum(synth.CHARACTERS[i][6] for i in range(len(synth.CHARACTERS))) + synth.WARBAND_START
        # Starting balances include a random silver/copper remainder per character.
        self.assertAlmostEqual(start / synth.G, expected, delta=len(synth.CHARACTERS))

    def test_transfers_net_to_zero_whatever_the_end_time(self):
        # Regression: the receiving leg of an alt mail could land after --end.
        for seed in range(4):
            for hour in range(0, 24, 3):
                db = synth.generate(days=10, seed=seed, end=END - END % 86400 + hour * 3600)
                net = sum(tx["a"] for c in db["chars"].values() for tx in c["tx"] if tx["k"] == "xfer_mail")
                self.assertEqual(net, 0, (seed, hour))

    def test_same_names_on_different_realms_are_distinguished(self):
        conn = sqlite3.connect(":memory:")
        self.conn.backup(conn)
        conn.execute("UPDATE characters SET name = 'Twin' WHERE char_key IN ('Aurelia-Area52', 'Vexis-Stormrage')")
        names = {p["key"]: p["name"] for p in dashboard.dashboard_data(conn, mariposa.CATEGORIES)["pockets"]}
        self.assertEqual(names["Aurelia-Area52"], "Twin (Area 52)")
        self.assertEqual(names["Vexis-Stormrage"], "Twin (Stormrage)")

    def test_render_escapes_script_breakout(self):
        conn = sqlite3.connect(":memory:")
        self.conn.backup(conn)
        conn.execute("UPDATE transactions SET ref = '</script><b>x' WHERE rowid = 1")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "dash.html"
            dashboard.render_dashboard(conn, out, mariposa.CATEGORIES)
            html = out.read_text(encoding="utf-8")
        self.assertNotIn(dashboard.PLACEHOLDER, html)
        self.assertNotIn("</script><b>", html)
        payload = html.split('id="mariposa-data">', 1)[1].split("</script>", 1)[0]
        self.assertIn("</script><b>x", json.dumps(json.loads(payload)["tx"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
