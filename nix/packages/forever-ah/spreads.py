"""free money that isnt crafting: cross-house flips (buy at blackwater, sell here) nd listings under wat a
vendor pays."""
from collections import defaultdict


def spreads(args, db, snaps, now, bw, items, book):
    """(flips, vendor) 4 th site. book(snapshot id) is {item: (median, floor, qty, listings)}"""
    last = snaps[-1][0]
    # buy in th quiet neutral house, sell here; 15% neutral cut is classic's, unverified 4 forever
    def open_spreads(here, there):
        out = {}
        for i in here.keys() & there.keys():
            buy, sell = there[i][1], here[i][1] * 0.95
            if here[i][3] >= 8 and there[i][3] >= 2 and sell > buy * 1.5 and sell - buy >= 2000:
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

    flips = [{"id": i, "name": (items.get(i) or (None,))[0] or f"item {i}", "buy": buy, "buy_listings": bw[i][3],
              "sell": now[i][1], "sell_listings": now[i][3], "profit": profit, "open": open_count[i]}
             for i, (buy, profit) in open_spreads(now, bw).items()]
    flips.sort(key=lambda f: -f["profit"])

    # listed under wat a vendor pays: buy nd vendor it. gear only lists in whole silvers, so undercutting a wall
    # at 4s lands on 3s even when it vendors 4 3s07c. th scan only knows th floor; raw listings (watched items)
    # say how many r actually under
    under = defaultdict(int)
    for i, p, q in db.execute("select item_id, unit_price, quantity from auction where snapshot_id = ?", (last,)):
        sell = (items.get(i) or (None, None))[1]
        if p is not None and sell and p < sell:
            under[i] += q
    floors = [book(sid) for sid, _ in snaps]
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
