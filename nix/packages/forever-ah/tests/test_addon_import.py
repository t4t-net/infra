"""addon-import puts each dump, poll nd deposit in th house it came from: booty bay's dump landed in 111 on
2026-11-18 nd would have priced th whole site off blackwater's book"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import NOW, fixture_db

import forever_ah  # noqa: E402

LINEN = 2589
NEUTRAL = '["ah"] = { ["kind"] = "neutral", ["npc"] = 2622, ["zone"] = "Stranglethorn Vale", ["subzone"] = "Booty Bay" },'
FACTION = '["ah"] = { ["kind"] = "faction", ["npc"] = 8719, ["npc_faction"] = "Alliance", ["zone"] = "Stormwind City" },'


def scan(t, n, ah=""):
    return f'{{ ["server_time"] = {t}, ["character"] = "test", ["n"] = {n}, {ah} ["format"] = 3, ["events"] = {{ {{ ["ms"] = 5, ["n"] = {n} }}, }}, ["rows"] = {{ "{LINEN}\\t20\\t240\\t0\\t0\\t3\\t\\t", }}, }},'


def poll(t, ah=""):
    return f'{{ ["t"] = {t}, ["c"] = "test", ["item"] = {LINEN}, ["n"] = 1, ["ms"] = 9, ["rows"] = "12:20:99{t}:3600:1", {ah} }},'


SAVEDVARS = f"""
ForeverScanDB = {{
["scans"] = {{
{scan(NOW - 400, 50000)}
{scan(NOW - 300, 6100)}
{scan(NOW - 200, 50000, NEUTRAL)}
{scan(NOW - 100, 6000, FACTION)}
}},
["watch_polls"] = {{
{poll(NOW - 90)}
{poll(NOW - 80, '["ah"] = "neutral",')}
{poll(NOW - 70, '["ah"] = "faction",')}
{{ ["t"] = {NOW - 60}, ["c"] = "test", ["item"] = {LINEN}, ["n"] = 0, ["rows"] = "", ["passive"] = true, ["ah"] = "faction", }},
{poll(NOW - 59, '["ah"] = "faction", ["passive"] = true,')}
}},
["deposits"] = {{ [{LINEN}] = {{ ["t"] = {NOW}, ["kind"] = "commodity", ["costs"] = "1:1:5 3:20:60" }}, }},
["deposits_neutral"] = {{ [{LINEN}] = {{ ["t"] = {NOW}, ["kind"] = "commodity", ["costs"] = "1:1:25 3:20:300" }}, }},
}}
"""


class AddonImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            path = fixture_db(tmp)
            db = sqlite3.connect(path)
            # an alliance reading from b4 addon_deposit had a house, so th migration has something 2 carry over
            db.execute(f"insert into addon_deposit values ({LINEN}, 2, 1, 20, 1, 1)")
            db.commit()
            db.close()
            sv = Path(tmp) / "ForeverScan.lua"
            sv.write_text(SAVEDVARS)
            argv = ["forever-ah", "--db", str(path), "addon-import", str(sv)]
            with mock.patch.object(sys, "argv", argv):
                forever_ah.main()
            db = sqlite3.connect(path)
            cls.scans = dict(db.execute("select server_ts, house_id from addon_scan where character = 'test'"))
            cls.polls = dict(db.execute("select server_ts, house_id from addon_watch_poll where character = 'test'"))
            cls.deposits = sorted(db.execute(f"select house_id, duration, quantity, deposit from addon_deposit where item_id = {LINEN}"))
            db.close()

    def test_tagged_scans_go_where_the_addon_says(self):
        # sized like th other house on purpose: th tag wins over th fingerprint
        self.assertEqual((self.scans[NOW - 200], self.scans[NOW - 100]), (117, 111))

    def test_untagged_scans_are_sized_against_both_houses(self):
        self.assertEqual((self.scans[NOW - 400], self.scans[NOW - 300]), (111, 117))

    def test_polls(self):
        self.assertEqual((self.polls[NOW - 90], self.polls[NOW - 80], self.polls[NOW - 70]), (111, 117, 111))

    def test_empty_passive_polls_are_dropped(self):
        # th empty one is blizz clearing th list mid-refresh; th full read right after it is real
        self.assertNotIn(NOW - 60, self.polls)
        self.assertEqual(self.polls[NOW - 59], 111)

    def test_deposits_keep_both_houses(self):
        self.assertEqual(self.deposits, [(111, 1, 1, 5), (111, 2, 1, 20), (111, 3, 20, 60), (117, 1, 1, 25), (117, 3, 20, 300)])


if __name__ == "__main__":
    unittest.main()
