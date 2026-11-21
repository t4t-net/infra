"""blackwater flips: th looser margin 4 liquid items, nd counting th blackwater units cheap enough 2 flip"""
import unittest
from argparse import Namespace

import support  # noqa: F401  puts th package on sys.path

import schema  # noqa: E402
from spreads import spreads  # noqa: E402

ESSENCE = 7078


def setup(here_floor, bw_listings):
    """one alliance dump w essence at here_floor (8 auctions), one blackwater dump w raw listings bw_listings,
    [(unit_price, quantity)], or no raw rows at all if None"""
    db = schema.connect(":memory:")
    db.execute("insert into snapshot values (1, 1000, 'us', 111, 'alliance', 1000)")
    db.execute("insert into snapshot values (2, 1000, 'us', 117, 'blackwater', 1000)")
    db.execute("insert into price values (1, ?, 1, ?, ?, 300, 8)", (ESSENCE, here_floor, here_floor))
    lots = bw_listings or [(13595, 10), (13595, 5)]
    db.execute("insert into price values (2, ?, 1, ?, ?, ?, ?)",
               (ESSENCE, lots[0][0], lots[0][0], sum(q for _, q in lots), len(lots)))
    for n, (p, q) in enumerate(bw_listings or ()):
        db.execute("insert into auction values (2, ?, ?, ?, ?, 'LONG')", (n, ESSENCE, p, q))

    def book(sid):
        return {i: (med, mn, q, n) for i, med, mn, q, n in db.execute(
            "select item_id, median_unit, min_unit, quantity, auctions from price where snapshot_id = ?", (sid,))}

    return db, book


def flips(here_floor, bw_listings, liquid):
    db, book = setup(here_floor, bw_listings)
    args = Namespace(blackwater=117, margin=1.5, liquid_margin=1.25)
    items = {ESSENCE: ("Essence of Fire", None, None)}
    out, _ = spreads(args, db, [(1, 1000)], book(1), book(2), 2, items, book, liquid)
    return out


class Spreads(unittest.TestCase):
    # 1g80s here is 1g71s after th cut: 1.26x th 1g35s95c buy, under 1.5 but over 1.25
    def test_liquid_flip_opens_on_the_thinner_margin(self):
        self.assertEqual(flips(18000, None, set()), [])
        (f,) = flips(18000, None, {ESSENCE})
        self.assertTrue(f["liquid"])
        self.assertEqual(f["profit"], 17100 - 13595)

    def test_counts_only_units_that_flip_at_their_own_price(self):
        # 13700 * 1.25 = 17125 > 17100, so th 20 at 13700 r up but dont flip
        (f,) = flips(18000, [(13595, 10), (13700, 20), (20000, 5)], {ESSENCE})
        self.assertEqual((f["buy_cheap"], f["buy_qty"]), (10, 35))

    def test_no_raw_blackwater_listings_is_unknown_not_zero(self):
        (f,) = flips(18000, None, {ESSENCE})
        self.assertIsNone(f["buy_cheap"])


if __name__ == "__main__":
    unittest.main()
