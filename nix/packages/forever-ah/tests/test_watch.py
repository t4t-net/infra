"""watch fills (th cheapest-first sweep + seller counts) nd merging them w th api's. see MARKET.md"""
import sqlite3
import tempfile
import unittest

from support import fixture_db

import fills  # noqa: E402
import market  # noqa: E402
import observe  # noqa: E402
from fills import Fill  # noqa: E402
from observe import Listing, Observation  # noqa: E402


def level(price, q, owners=1, left=86000):
    return Listing(price, q, time_left_s=left, owners=owners)


def poll(t, *levels, complete=True):
    return Observation(1, t, "watch", tuple(levels), complete)


def run(*series):
    return [(f.kind, f.unit_price, f.quantity, f.confidence, f.lower_bound) for f in fills.watch_fills(list(series))]


class RealPolls(unittest.TestCase):
    """sweeps ellie's addon actually saw on 2026-11-11, house 111"""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            cls.obs = observe.watch_observations(sqlite3.connect(fixture_db(tmp)), 111)

    def window(self, item, t_from):
        return [(f.kind, f.unit_price, f.quantity, f.confidence, f.lower_bound)
                for f in fills.watch_fills(self.obs[item]) if f.t_from == t_from]

    def test_bronze_sweep(self):
        # 170, 175 nd 176 cleared, then 20 off th 177 wall: 244 bronze bars in under a minute
        self.assertEqual(self.window(2841, 1794451400), [
            ("sale", 170, 26, "high", False), ("sale", 175, 170, "high", False), ("sale", 176, 28, "high", False),
            ("sale", 177, 20, "high", False), ("pull", 185, 11, "low", False)])

    def test_copper_60c(self):
        # 33 -> 8 w th same seller is a buy fr. then it vanished as 72c/75c showed up: buy or relist, cant tell
        self.assertEqual(self.window(2840, 1794451405), [("sale", 60, 25, "high", False)])
        self.assertEqual(self.window(2840, 1794451465), [("sale", 60, 8, "low", False)])

    def test_invariants(self):
        for item, series in self.obs.items():
            for a, b in zip(series, series[1:]):
                got = [f for f in fills.watch_fills([a, b])]
                prices = {l.unit_price: l.quantity for l in a.listings}
                for f in got:
                    # every fill is a level th earlier poll had, nd never more than was there
                    self.assertIn(f.unit_price, prices, item)
                    self.assertLessEqual(f.quantity, prices[f.unit_price], item)
                self.assertLessEqual(sum(f.quantity for f in got), sum(prices.values()), item)


class Sweep(unittest.TestCase):
    def test_partial_buy_proves_th_vanished_levels_below(self):
        self.assertEqual(run(poll(0, level(10, 5), level(11, 50)), poll(60, level(11, 40))),
                         [("sale", 10, 5, "high", False), ("sale", 11, 10, "high", False)])

    def test_vanished_then_untouched_is_low(self):
        self.assertEqual(run(poll(0, level(10, 5), level(11, 50)), poll(60, level(11, 50))),
                         [("sale", 10, 5, "low", False)])

    def test_whole_book_gone_is_low(self):
        self.assertEqual(run(poll(0, level(10, 5), level(11, 50)), poll(60)),
                         [("sale", 10, 5, "low", False), ("sale", 11, 50, "low", False)])

    def test_owners_on_th_partial_level(self):
        down = run(poll(0, level(10, 50, owners=3)), poll(60, level(10, 30, owners=2)))
        up = run(poll(0, level(10, 50, owners=3)), poll(60, level(10, 30, owners=4)))
        self.assertEqual(down, [("sale", 10, 20, "low", False)])
        self.assertEqual(up, [("sale", 10, 20, "high", True)])

    def test_above_th_sweep_is_a_pull(self):
        # 10 untouched, so th 11 nd 12 drops cant b buyers
        self.assertEqual(run(poll(0, level(10, 5), level(11, 9, owners=2), level(12, 4)),
                             poll(60, level(10, 5), level(11, 6, owners=2))),
                         [("pull", 11, 3, "low", False), ("pull", 12, 4, "high", False)])

    def test_expiry_doesnt_stop_th_sweep(self):
        self.assertEqual(run(poll(0, level(10, 5, left=30), level(11, 50)), poll(60, level(11, 45))),
                         [("expire", 10, 5, "high", False), ("sale", 11, 5, "high", False)])

    def test_fresh_undercut_is_ignored(self):
        self.assertEqual(run(poll(0, level(10, 50)), poll(60, level(9, 20), level(10, 45))),
                         [("sale", 10, 5, "high", False)])

    def test_capped_poll_doesnt_invent_pulls_past_wat_it_saw(self):
        self.assertEqual(run(poll(0, level(10, 5), level(11, 5), level(50, 5)),
                             poll(60, level(10, 5), level(11, 5), complete=False)), [])

    def test_sessions_too_far_apart_r_skipped(self):
        self.assertEqual(run(poll(0, level(10, 5)), poll(fills.WATCH_MAX_GAP + 1)), [])
        self.assertEqual(fills.watch_spans([poll(0), poll(60), poll(60 + fills.WATCH_MAX_GAP + 1)]), [(0, 60)])


def fill(source, t_from, t_to, q=1, kind="sale"):
    return Fill(1, t_from, t_to, 10, q, source, kind)


class Merge(unittest.TestCase):
    dumps = [0, 3600, 7200]

    def test_covered_window_uses_th_watch(self):
        api = [fill("api", 0, 3600, 50), fill("api", 3600, 7200, 7)]
        watch = [fill("watch", 100, 160, 20), fill("watch", 2000, 2060, 25)]
        got = fills.merge(api, watch, [(60, 3500)], self.dumps)
        self.assertEqual(sorted((f.source, f.quantity) for f in got), [("api", 7), ("watch", 20), ("watch", 25)])

    def test_thin_coverage_keeps_th_api(self):
        api = [fill("api", 0, 3600, 50)]
        watch = [fill("watch", 100, 160, 20)]
        got = fills.merge(api, watch, [(100, 700)], self.dumps)
        self.assertEqual([(f.source, f.quantity) for f in got], [("api", 50)])

    def test_live_tail_after_th_last_dump_is_kept(self):
        watch = [fill("watch", 7300, 7360, 3)]
        got = fills.merge([], watch, [(7300, 7360)], self.dumps)
        self.assertEqual([(f.source, f.t_to) for f in got], [("watch", 7360)])

    def test_a_sweep_over_several_polls_is_one_spree(self):
        f = [fill("watch", 0, 60), fill("watch", 60, 120), fill("watch", 120, 180), fill("watch", 5000, 5060)]
        self.assertEqual(fills.tally(f, 0)[3][1], 2)
        self.assertEqual(fills.sprees([0, 3600, 7200]), 3)

    def test_covered_time_is_th_union(self):
        self.assertEqual(market.covered_seconds([(0, 3600), (3000, 3700), (5000, 5060)]), 3760)
        self.assertEqual(market.covered_seconds([]), 0)

    def test_tally_ignores_expiries(self):
        sold, pulled, _, _ = fills.tally([fill("watch", 0, 60, 5), fill("watch", 0, 60, 9, "expire")], 0)
        self.assertEqual((sold[1], pulled[1]), ([5, 50], 0))


if __name__ == "__main__":
    unittest.main()
