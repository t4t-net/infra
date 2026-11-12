"""observations → fills: wat sold (nd wat got pulled) between two looks at an item's book. see MARKET.md

each source gets its own inference, all emitting Fill, nd merge() picks one source per item per api window
so nothing is counted twice
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
    kind: str                       # "sale", "pull" (cancelled / reposted), or "expire"
    confidence: str = "high"        # "low" when a cancel wud have looked th same
    lower_bound: bool = False       # th real quantity is bigger (listings joined th level while it sold)


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


WATCH_MAX_GAP = 600  # polls of an item further apart than this r separate sessions, not one window


def watch_fills(series, max_gap=WATCH_MAX_GAP):
    """watch polls: th book as price levels. commodities trade by three rules: buyers take th cheapest units
    first, a buy can take PART of a listing, nd a cancel always pulls a WHOLE one. so walk th earlier poll's
    levels from th cheapest up (matched by price; new levels r fresh undercuts nobody cud have bought yet):

    - th sweep: levels tht vanished, then th first level tht shrank but survived, r wat buyers ate. vanished
      levels only count as proven sales when th sweep ends in tht partial buy; if it stops at an untouched
      level, a seller cancelling looks th same, so they r low confidence
    - a vanished level w less time left than th gap probably expired
    - above th sweep, any drop is a pull, since a buyer wud have taken th cheaper units first
    - seller counts on th partial level: same = a buy (cancels remove whole listings), down = maybe a cancel
      (low), up = someone listed into it while it sold, so th drop undercounts (lower bound)
    """
    for a, b in zip(series, series[1:]):
        gap = b.t - a.t
        if gap > max_gap:
            continue
        after = {l.unit_price: l for l in b.listings}
        # past a capped poll's last level, missing just means unseen
        seen_to = math.inf if b.complete else max((l.unit_price for l in b.listings), default=-1)

        def fill(l, q, kind, confidence="high", lower_bound=False):
            return Fill(a.item_id, a.t, b.t, l.unit_price, q, a.source, kind, confidence, lower_bound)

        sweeping, swept = True, []
        for l in sorted(a.listings, key=lambda l: l.unit_price):
            if l.unit_price > seen_to:
                break
            now = after.get(l.unit_price)
            drop = l.quantity - (now.quantity if now else 0)
            if now is None and l.time_left_s is not None and l.time_left_s < gap:
                yield fill(l, l.quantity, "expire")
            elif not sweeping:
                if drop > 0:
                    gone = now is None or (now.owners is not None and l.owners is not None and now.owners < l.owners)
                    yield fill(l, drop, "pull", "high" if gone else "low")
            elif now is None:
                swept.append(l)
            else:
                proven = drop > 0
                for v in swept:
                    yield fill(v, v.quantity, "sale", "high" if proven else "low")
                swept = []
                if proven:
                    if now.owners is None or l.owners is None or now.owners == l.owners:
                        yield fill(l, drop, "sale")
                    elif now.owners < l.owners:
                        yield fill(l, drop, "sale", "low")
                    else:
                        yield fill(l, drop, "sale", lower_bound=True)
                sweeping = False
        # th whole seen book vanished. buyers clearing it all, or everyone cancelling, cant b told apart
        for v in swept:
            yield fill(v, v.quantity, "sale", "low")


def watch_spans(series, max_gap=WATCH_MAX_GAP):
    """th (from, to) stretches th watch actually covered 4 one item"""
    return [(a.t, b.t) for a, b in zip(series, series[1:]) if b.t - a.t <= max_gap]


def merge(api, watch, spans, dump_times, coverage=0.8):
    """one item's fills, one source per api window: th watch's where it covered at least `coverage` of th
    window, th api's everywhere else. watch fills outside every api window (th live tail after th last dump)
    r kept, thats th freshest data there is"""
    out = []
    windows = list(zip(dump_times, dump_times[1:]))
    for t0, t1 in windows:
        seen = sum(max(0, min(b, t1) - max(a, t0)) for a, b in spans)
        if seen >= coverage * (t1 - t0):
            out += [f for f in watch if t0 < f.t_to <= t1]
        else:
            out += [f for f in api if f.t_from == t0 and f.t_to == t1]
    if windows:
        out += [f for f in watch if not windows[0][0] < f.t_to <= windows[-1][1]]
    else:
        out += list(watch)
    return out


def tally(fills, recent_since):
    """per item: sold [units, copper], pulled units, units sold in windows ending at or after recent_since,
    nd how many distinct windows had a sale (sprees). expiries count as neither. th spree count is th api's
    hourly-window notion; minute-level watch fills need real time-gap clustering (MARKET.md), not this"""
    sold = defaultdict(lambda: [0, 0])
    pulled = defaultdict(int)
    recent = defaultdict(int)
    spree_windows = defaultdict(set)
    for f in fills:
        if f.kind == "pull":
            pulled[f.item_id] += f.quantity
            continue
        if f.kind != "sale":
            continue
        sold[f.item_id][0] += f.quantity
        sold[f.item_id][1] += f.quantity * f.unit_price
        spree_windows[f.item_id].add(f.t_to)
        if f.t_to >= recent_since:
            recent[f.item_id] += f.quantity
    return sold, pulled, recent, defaultdict(int, {i: len(w) for i, w in spree_windows.items()})
