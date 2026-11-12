"""market.py's pure helpers"""
import unittest

from support import HERE

import market  # noqa: E402
from fills import Fill  # noqa: E402
from observe import Listing  # noqa: E402

assert (HERE.parent / "market.py").exists(), "support puts th package on th path"

# th real copper bar book from 2026-11-11 18:43 (cheap end), api median 85c
COPPER = (Listing(60, 33), Listing(77, 44), Listing(78, 875), Listing(79, 109))


class WalkBook(unittest.TestCase):
    def test_ironforge_breastplate(self):
        # 16 bars: all from th 60c seller. 5 crafts (80): 33@60 + 44@77 + 3@78
        self.assertEqual(market.walk_book(COPPER, 16, 85), 960)
        self.assertEqual(market.walk_book(COPPER, 80, 85), 33 * 60 + 44 * 77 + 3 * 78)

    def test_past_th_end_goes_at_th_fallback(self):
        self.assertEqual(market.walk_book(COPPER[:1], 40, 85), 33 * 60 + 7 * 85)
        self.assertEqual(market.walk_book((), 3, 85), 255)

    def test_order_nd_bids_dont_matter(self):
        shuffled = (Listing(None, 99), COPPER[1], COPPER[0])
        self.assertEqual(market.walk_book(shuffled, 40, 85), 33 * 60 + 7 * 77)

    def test_fractional_quantities_from_smelting_chains(self):
        self.assertEqual(market.walk_book(COPPER, 0.5, 85), 30)


def sale(t, price, q=1):
    return Fill(1, t - 3600, t, price, q, "api", "sale")


class Prices(unittest.TestCase):
    def test_clearing_is_th_weighted_median(self):
        self.assertEqual(market.clearing_price([sale(0, 50, 1), sale(0, 60, 10), sale(0, 99, 2)]), 60)
        self.assertIsNone(market.clearing_price([]))

    def test_trend_is_copper_per_hour(self):
        # thorium-ish crash: 300 -> 200 over 2h
        self.assertAlmostEqual(market.trend_per_h([sale(0, 300), sale(3600, 250), sale(7200, 200)]), -50)
        self.assertIsNone(market.trend_per_h([sale(0, 300, 5)]))

    def test_realizable_undercuts_nd_caps_at_clearing(self):
        self.assertEqual(market.realizable(100, 1, None, None, None), 99)
        self.assertEqual(market.realizable(100, 1, 80, None, None), 80)

    def test_falling_prices_r_projected_rising_arent(self):
        self.assertEqual(market.realizable(100, 1, None, -10, 3), 69)
        self.assertEqual(market.realizable(100, 1, None, 10, 3), 99)

    def test_gear_cant_go_under_1s(self):
        self.assertEqual(market.realizable(100, 100, None, -50, 5), 100)

    def test_gear_undercuts_by_a_copper(self):
        # heavy copper maul wall at 12s05c: 12s04c now, not 11s like b4 th 2026-11-12 change
        self.assertEqual(market.realizable(1205, 100, None, None, None), 1204)


if __name__ == "__main__":
    unittest.main()
