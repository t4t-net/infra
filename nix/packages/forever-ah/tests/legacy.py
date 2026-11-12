"""th api sales loop exactly as market_data ran it b4 fills.py, kept as th reference test_fills checks against"""
import math
from collections import defaultdict


def legacy_sales(db, snaps, dry_dumps):
    """th api sales rule as market_data has always run it, kept as th reference fills.py is checked against.
    (sold [units, copper], pulled units, recent units, dumps w a sale) per item"""
    # sales: listings tht vanished w time left. buyers take th cheapest first, so one tht vanished while a cheaper
    # listing from th same dump is still up was pulled (cancelled or reposted), not bought. th next dump's floor
    # isnt good enough 4 this: fresh undercuts land below it nd turned real sales on busy bars into "cancels"
    sold = defaultdict(lambda: [0, 0])
    pulled = defaultdict(int)
    recent = defaultdict(int)  # units sold in th last dry_dumps dumps
    # dumps w any sales. buyers come in sprees (heavy dynamite: 142 units in 4 buyouts over 12h, nothing between),
    # so timing a listing off units/h said ~5m when th real answer was th next spree, hours away
    events = defaultdict(int)
    for n, ((a, _), (b, _)) in enumerate(zip(snaps, snaps[1:])):
        after = dict(db.execute("select auction_id, quantity from auction where snapshot_id = ?", (b,)))
        rows = db.execute("select auction_id, item_id, unit_price, quantity, time_left from auction where snapshot_id = ?",
                          (a,)).fetchall()
        floor = {}
        for aid, iid, price, _, _ in rows:
            if aid in after and price is not None and price < floor.get(iid, math.inf):
                floor[iid] = price
        bought = set()
        for aid, iid, price, q, tl in rows:
            gone = q - after.get(aid, 0)
            if price is None or tl == "SHORT" or gone <= 0:
                continue
            if price > floor.get(iid, math.inf):
                pulled[iid] += gone
                continue
            bought.add(iid)
            sold[iid][0] += gone
            sold[iid][1] += gone * price
            if n >= len(snaps) - 1 - dry_dumps:
                recent[iid] += gone
        for iid in bought:
            events[iid] += 1
    return sold, pulled, recent, events
