"""market.py's pure helpers"""
import unittest

from support import HERE

import market  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
