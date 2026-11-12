"""observations → fills: wat sold (nd wat got pulled) between two looks at an item's book. see MARKET.md

each source gets its own inference, all emitting Fill. only th api's exists so far; th watch sweep comes next
"""
import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Fill:
    item_id: int
    t_from: int                     # it happened somewhere between these two looks
    t_to: int
    unit_price: int
    quantity: int
    source: str
    kind: str                       # "sale", or "pull" 4 cancelled / reposted


def api_fills(series):
    """listings tht vanished (or shrank) w time left. buyers take th cheapest first, so one tht went while a
    cheaper listing from th same dump survived was pulled, not bought. th next dump's floor isnt good enough
    4 this: fresh undercuts land below it nd turned real sales on busy bars into "pulls". SHORT listings may
    just have expired, nd bid-only ones arent buyouts, so neither counts"""
    for a, b in zip(series, series[1:]):
        after = {l.auction_id: l.quantity for l in b.listings}
        floor = min((l.unit_price for l in a.listings if l.auction_id in after and l.unit_price is not None),
                    default=math.inf)
        for l in a.listings:
            gone = l.quantity - after.get(l.auction_id, 0)
            if l.unit_price is None or l.time_left == "SHORT" or gone <= 0:
                continue
            yield Fill(a.item_id, a.t, b.t, l.unit_price, gone, a.source,
                       "pull" if l.unit_price > floor else "sale")


def tally(fills, recent_since):
    """per item: sold [units, copper], pulled units, units sold in windows ending at or after recent_since,
    nd how many distinct windows had a sale (sprees)"""
    sold = defaultdict(lambda: [0, 0])
    pulled = defaultdict(int)
    recent = defaultdict(int)
    spree_windows = defaultdict(set)
    for f in fills:
        if f.kind == "pull":
            pulled[f.item_id] += f.quantity
            continue
        sold[f.item_id][0] += f.quantity
        sold[f.item_id][1] += f.quantity * f.unit_price
        spree_windows[f.item_id].add(f.t_to)
        if f.t_to >= recent_since:
            recent[f.item_id] += f.quantity
    return sold, pulled, recent, {i: len(w) for i, w in spree_windows.items()}
