"""th discord flip alert: wat counts as new, wat clears th bar, nd wat th message says"""
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import support  # noqa: F401  puts th package on sys.path

import export  # noqa: E402


def flip(i, name, profit, liquid=False, **kw):
    return {"id": i, "name": name, "buy": 13596, "buy_listings": 6, "buy_qty": 37, "sell": 28599,
            "sell_listings": 40, "sell_qty": 61, "profit": profit, "open": 1, "liquid": liquid, "sold": 438,
            "sold_maybe": 0, "sold_at": 17000, "tracked_h": 23.0, "war": None, "wait_h": 0.5, "trend_per_h": None,
            "floor_dumps": 0, **kw}


class Alert(unittest.TestCase):
    def run_alert(self, tmp, flips, was_open, min_profit=5000):
        tmp = Path(tmp)
        (tmp / "data.json").write_text(json.dumps({"dump": 2, "dumps": 24, "flips": flips}))
        (tmp / "state.json").write_text(json.dumps({"dump": 1, "open": was_open}))
        (tmp / "hook").write_text("https://discord.invalid/hook")
        args = Namespace(data=tmp / "data.json", state=tmp / "state.json", webhook_file=tmp / "hook",
                         min_profit=min_profit, site=None)
        with mock.patch("urllib.request.urlopen") as post:
            export.alert(args, None)
        return json.loads(post.call_args[0][0].data)["content"] if post.called else None

    def test_liquid_flip_alerts_under_min_profit_and_goes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = self.run_alert(tmp, [flip(1, "Big Sword", 200000), flip(7078, "Essence of Fire", 13573, liquid=True),
                                       flip(3, "Small Sword", 9000)], was_open=[], min_profit=50000)
        lines = msg.splitlines()
        self.assertIn("2 new flips", lines[0])
        self.assertTrue(lines[1].startswith("**liquid** [Essence of Fire]"))
        self.assertIn("(37 up)", lines[1])
        self.assertIn("Big Sword", lines[3])
        self.assertNotIn("Small Sword", msg)

    def test_untested_when_sales_were_cheaper(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = self.run_alert(tmp, [flip(7078, "Essence of Fire", 13573, liquid=True)], was_open=[])
        self.assertIn("sold 438 in ~23h at 1g 70s avg, untested at this price", msg)

    def test_says_how_many_are_cheap_enough_once_blackwater_is_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = self.run_alert(tmp, [flip(7078, "Essence of Fire", 13573, liquid=True, buy_cheap=10)], was_open=[])
        self.assertIn("buy 1g 35s (10 of 37 cheap enough)", msg)

    def test_already_open_stays_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.run_alert(tmp, [flip(7078, "Essence of Fire", 13573, liquid=True)], was_open=[7078]))


if __name__ == "__main__":
    unittest.main()
