"""free money that isnt crafting: cross-house flips (buy at blackwater, sell here) nd listings under wat a
vendor pays."""
from collections import defaultdict


def spreads(args, db, snaps, now, bw, bw_sid, items, book, liquid):
    """(flips, vendor) 4 th site. book(snapshot id) is {item: (median, floor, qty, listings)}, bw_sid th
    blackwater snapshot bw came from, liquid th items tht sold --liquid-sold here in th window"""
    last = snaps[-1][0]

    # buy in th quiet neutral house, sell here; 15% neutral cut is classic's, unverified 4 forever. th margin
    # covers th price moving b4 u get back nd th listing tht never sells. stuff tht sells hundreds a day risks
    # less of both, so it gets a thinner one
    def flippable(i, buy, sell):
        return sell > buy * (args.liquid_margin if i in liquid else args.margin) and sell - buy >= 2000

    def open_spreads(here, there):
        out = {}
        for i in here.keys() & there.keys():
            buy, sell = there[i][1], here[i][1] * 0.95
            if here[i][3] >= 8 and there[i][3] >= 2 and flippable(i, buy, sell):
                out[i] = (buy, int(sell - buy))
        return out

    # how many dumps in th window each spread was open 4. blackwater only gets a new snapshot when its dump
    # changes, so each of our dumps pairs w th latest blackwater snapshot at or before it
    open_count = defaultdict(int)
    for sid, _ in snaps:
        ts = db.execute("select ts from snapshot where id = ?", (sid,)).fetchone()[0]
        bsid = db.execute("select id from snapshot where house_id = ? and ts <= ? order by ts desc limit 1",
                          (args.blackwater, ts)).fetchone()
        if bsid:
            for i in open_spreads(book(sid), book(bsid[0])):
                open_count[i] += 1

    # stability: wat th floor here did over th window. a sell side tht only just spiked 2 its top is a flip tht
    # closes b4 ur stuff arrives, a flat one isnt. dumps w nothing up dont count, `floor_dumps` says how many did
    floors = [book(sid) for sid, _ in snaps]

    def floor_range(i):
        seen = sorted(b[i][1] for b in floors if i in b)
        return {"floor_low": seen[0], "floor_med": seen[len(seen) // 2], "floor_high": seen[-1],
                "floor_dumps": len(seen)} if seen else {"floor_low": None, "floor_med": None, "floor_high": None,
                                                         "floor_dumps": 0}

    opened = open_spreads(now, bw)
    # th floor is one listing, th rest of th book can sit way over break-even. raw blackwater listings (tracked
    # since 2026-11-20) say how many units still flip at their own price. None b4 tht, not a fake 0
    cheap = defaultdict(int) if bw_sid is not None and db.execute(
        "select 1 from auction where snapshot_id = ? limit 1", (bw_sid,)).fetchone() else None
    if cheap is not None and opened:
        marks = ",".join("?" * len(opened))
        for i, p, q in db.execute(f"select item_id, unit_price, quantity from auction where snapshot_id = ? "
                                  f"and item_id in ({marks})", (bw_sid, *opened)):
            if p is not None and flippable(i, p, now[i][1] * 0.95):
                cheap[i] += q
    flips = [{"id": i, "name": (items.get(i) or (None,))[0] or f"item {i}", "buy": buy, "buy_listings": bw[i][3],
              "buy_qty": bw[i][2], "buy_cheap": cheap[i] if cheap is not None else None, "sell": now[i][1],
              "sell_listings": now[i][3], "sell_qty": now[i][2], "profit": profit, "open": open_count[i],
              "liquid": i in liquid, **floor_range(i)}
             for i, (buy, profit) in opened.items()]
    flips.sort(key=lambda f: -f["profit"])

    # listed under wat a vendor pays: buy nd vendor it. gear used 2 list in whole silvers (undercutting a 4s
    # wall landed on 3s even when it vendored 4 3s07c), copper-precise since 2026-11-12. th scan only knows
    # th floor; raw listings (tracked houses) say how many r actually under
    under = defaultdict(int)
    for i, p, q in db.execute("select item_id, unit_price, quantity from auction where snapshot_id = ?", (last,)):
        sell = (items.get(i) or (None, None))[1]
        if p is not None and sell and p < sell:
            under[i] += q
    vendor = []
    for i, (_, mn, q, n) in now.items():
        sell = (items.get(i) or (None, None))[1]
        if not sell or mn >= sell:
            continue
        streak = 0
        for b in reversed(floors):
            if i not in b or b[i][1] >= sell:
                break
            streak += 1
        vendor.append({"id": i, "name": items[i][0] or f"item {i}", "floor": mn, "vendor": sell, "profit": sell - mn,
                       "under": under.get(i), "listings": n, "open": streak})
    vendor.sort(key=lambda v: -v["profit"])
    vendor = vendor[:20]
    return flips, vendor
