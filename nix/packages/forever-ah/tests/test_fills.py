"""fills.py's api rule: same answers as th loop market_data has always run, nd each branch of th rule by hand"""
import sqlite3
import tempfile
import unittest

from support import NOW, fixture_db

import fills  # noqa: E402
import legacy  # noqa: E402
import observe  # noqa: E402
from observe import Listing, Observation  # noqa: E402

DRY_DUMPS = 3


def api(t, *listings):
    return Observation(1, t, "api", tuple(Listing(*l) for l in listings))


def run(*series):
    return list(fills.api_fills(list(series)))


class MatchesLegacy(unittest.TestCase):
    """every item in th fixture: sold units nd copper, pulled, recent, nd spree count all equal th old loop's"""

    def test_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = sqlite3.connect(fixture_db(tmp))
            dumps = observe.api_dumps(db, 111, NOW - 24 * 3600)
            old = legacy.legacy_sales(db, dumps, DRY_DUMPS)
            recent_since = dumps[max(0, len(dumps) - DRY_DUMPS)][1]
            new = fills.tally((f for s in observe.api_observations(db, dumps).values() for f in fills.api_fills(s)),
                              recent_since)
        names = ("sold", "pulled", "recent", "sprees")
        for name, o, n in zip(names, old, new):
            # defaultdicts: compare only wat each side actually filled in
            o, n = {k: v for k, v in o.items() if v}, {k: v for k, v in n.items() if v}
            self.assertEqual(o, n, name)
        # nd make sure th fixture actually exercises th rule, not 2 empty dicts agreeing
        self.assertGreater(len(old[0]), 50)
        self.assertGreater(len(old[1]), 20)


class Rule(unittest.TestCase):
    def test_vanished_cheapest_is_a_sale(self):
        f = run(api(0, (50, 5, 1, "LONG"), (60, 5, 2, "LONG")), api(3600, (60, 5, 2, "LONG")))
        self.assertEqual([(x.kind, x.unit_price, x.quantity) for x in f], [("sale", 50, 5)])

    def test_vanished_above_a_survivor_is_a_pull(self):
        # th 50 is still up, so a buyer wudnt have taken th 60 first
        f = run(api(0, (50, 5, 1, "LONG"), (60, 5, 2, "LONG")), api(3600, (50, 5, 1, "LONG")))
        self.assertEqual([(x.kind, x.unit_price) for x in f], [("pull", 60)])

    def test_partial_buy_counts_th_drop(self):
        f = run(api(0, (50, 20, 1, "LONG")), api(3600, (50, 12, 1, "LONG")))
        self.assertEqual([(x.kind, x.quantity) for x in f], [("sale", 8)])

    def test_everything_gone_is_all_sales(self):
        f = run(api(0, (50, 5, 1, "LONG"), (70, 1, 2, "MEDIUM")), api(3600))
        self.assertEqual(sorted((x.kind, x.unit_price) for x in f), [("sale", 50), ("sale", 70)])

    def test_fresh_undercut_doesnt_turn_sales_into_pulls(self):
        # someone listed at 40 after th 50 sold. only listings from th SAME earlier dump set th floor
        f = run(api(0, (50, 5, 1, "LONG")), api(3600, (40, 5, 9, "VERY_LONG")))
        self.assertEqual([x.kind for x in f], ["sale"])

    def test_short_nd_bid_only_dont_count(self):
        f = run(api(0, (50, 5, 1, "SHORT"), (None, 1, 2, "LONG")), api(3600))
        self.assertEqual(f, [])

    def test_growth_isnt_a_fill(self):
        f = run(api(0, (50, 5, 1, "LONG")), api(3600, (50, 9, 1, "LONG")))
        self.assertEqual(f, [])

    def test_fill_carries_its_window(self):
        (f,) = run(api(100, (50, 5, 1, "LONG")), api(3700))
        self.assertEqual((f.t_from, f.t_to, f.source, f.item_id), (100, 3700, "api", 1))

    def test_tally_counts_sprees_per_window(self):
        f = run(api(0, (50, 5, 1, "LONG"), (51, 5, 2, "LONG")), api(10, (51, 5, 2, "LONG")), api(20), api(30))
        sold, pulled, recent, sprees = fills.tally(f, recent_since=20)
        self.assertEqual((sold[1], sprees[1], recent[1], pulled[1]), ([10, 505], 2, 5, 0))


if __name__ == "__main__":
    unittest.main()
