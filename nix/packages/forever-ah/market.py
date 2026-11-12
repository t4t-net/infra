"""th market model behind th site. see MARKET.md 4 th rebuild this is waiting on."""
import math
import time
from collections import defaultdict
from itertools import accumulate


import fills
import observe
from crafts import craft_tables
from spreads import spreads
from game import AUCTION_DURATIONS, GATHERED, deposit


def g(c):
    if c is None:
        return "-"
    s = "-" if c < 0 else ""
    c = abs(c)
    return f"{s}{c/10000:.2f}g" if c >= 10000 else f"{s}{c/100:.1f}s" if c >= 100 else f"{s}{int(c)}c"


def analyze(args, db):
    """Buy every mat at median, sell by undercutting th lowest listing, minus th 5% AH cut."""
    ts = db.execute("select max(ts) from snapshot where house_id = ?", (args.house,)).fetchone()[0]
    ah = {}
    for item_id, med, mn, n in db.execute(
            "select item_id, median_unit, min_unit, auctions from price p join snapshot s on s.id = p.snapshot_id "
            "where s.ts = ? and s.house_id = ? order by quantity", (ts, args.house)):
        ah[item_id] = (med, mn, n)
    items = {i: (name, buy) for i, name, buy in db.execute("select id, name, purchase_price from item_live")}

    rows = []
    for rid, name, crafted, cmin, cmax in db.execute(
            "select id, name, crafted_item_id, crafted_min, crafted_max from recipe where profession_id = ? and crafted_item_id is not null",
            (args.profession,)):
        out = ah.get(crafted)
        if not out or out[2] < args.min_auctions:
            continue
        cost, ok = 0, True
        for iid, q in db.execute("select item_id, quantity from reagent where recipe_id = ?", (rid,)):
            if iid in ah:
                cost += ah[iid][0] * q
            elif items.get(iid, (None, None))[1]:
                cost += items[iid][1] * q
            else:
                ok = False
        if not ok or cost == 0:
            continue
        revenue = out[1] * (cmin + cmax) / 2 * 0.95
        rows.append((revenue - cost, name, cost, revenue, out[2]))

    rows.sort(reverse=True)
    print(f"house {args.house} @ {time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))}")
    print(f"{'recipe':<36}{'buy mats':>10}{'sell(min)':>11}{'profit':>10}{'#ah':>5}")
    for profit, name, cost, revenue, n in rows[:args.top]:
        print(f"{name[:35]:<36}{g(cost):>10}{g(revenue):>11}{g(profit):>10}{n:>5}")


LIVE_S = 900  # a book seen this recently counts as real-time on th site, older is "delayed"


def clearing_price(sales):
    """th quantity-weighted median price sure sales went 4, or None w no sales"""
    lots = sorted((f.unit_price, f.quantity) for f in sales)
    total, acc = sum(q for _, q in lots), 0
    for price, q in lots:
        acc += q
        if acc * 2 >= total:
            return price
    return None


def trend_per_h(sales):
    """least squares slope of sure-sale prices over time, weighted by quantity, in copper per hour. None
    until sales landed at two different times"""
    pts = [(f.t_to / 3600, f.unit_price, f.quantity) for f in sales]
    w = sum(q for _, _, q in pts)
    if not w or len({x for x, _, _ in pts}) < 2:
        return None
    mx = sum(x * q for x, _, q in pts) / w
    my = sum(y * q for _, y, q in pts) / w
    return sum(q * (x - mx) * (y - my) for x, y, q in pts) / sum(q * (x - mx) ** 2 for x, _, q in pts)


def realizable(floor, step, clearing, trend, wait_h):
    """wat listing one now shud actually fetch: one step (1c commodities, 1s gear) under th floor, never above
    wat sales actually cleared at, nd if th price is falling, wat its fallen 2 by th time urs sells. a rising
    trend is NOT projected: promising tomorrow's higher price is th overconfident kind of wrong. never under
    th AH's minimum, which is th step"""
    prices = [p for p in (floor - step if floor is not None else None, clearing) if p is not None]
    if not prices:
        return None
    price = min(prices)
    if trend is not None and trend < 0 and wait_h:
        price += trend * wait_h
    return max(step, round(price))


def walk_book(listings, q, fallback_unit):
    """copper 4 q units bought cheapest first, not q x th median: on th 2026-11-11 copper bar book th median
    (85c) overstated a single 16-bar craft by 42%. past th book's end th rest goes at fallback_unit"""
    cost, left = 0, q
    for l in sorted((l for l in listings if l.unit_price is not None), key=lambda l: l.unit_price):
        take = min(left, l.quantity)
        cost += take * l.unit_price
        left -= take
        if left <= 0:
            break
    return cost + left * fallback_unit


def covered_seconds(spans):
    """length of th union of (from, to) stretches"""
    total, end = 0, None
    for a, b in sorted(spans):
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


def market_data(args, db):
    """Everything th site shows, from th dumps in th last args.hours."""
    since = (args.now or int(time.time())) - args.hours * 3600
    snaps = observe.api_dumps(db, args.house, since)
    if not snaps:
        raise SystemExit(f"no snapshots of house {args.house} in th last {args.hours}h")
    bw_last = db.execute("select id from snapshot where house_id = ? order by ts desc limit 1", (args.blackwater,)).fetchone()

    def book(sid):
        return {i: (med, mn, q, n) for i, med, mn, q, n in db.execute(
            "select item_id, median_unit, min_unit, quantity, auctions from price where snapshot_id = ? order by quantity", (sid,))}

    now, then = book(snaps[-1][0]), book(snaps[0][0])
    bw = book(bw_last[0]) if bw_last else {}
    items = {i: (n, s, b) for i, n, s, b in db.execute("select id, name, sell_price, purchase_price from item_live")}

    # sales: see fills.api_fills 4 th rule. sprees (dumps w any sale) matter cuz buyers come in bursts (heavy
    # dynamite: 142 units in 4 buyouts over 12h, nothing between), so timing a listing off units/h said ~5m when
    # th real answer was th next spree, hours away
    # th addon's watch polls (in th window, nothing after --now) take over th api windows they covered, nd their
    # live tail after th last dump is th freshest sales data there is. see fills.merge
    now_t = args.now or int(time.time())
    obs = observe.api_observations(db, snaps)
    watch = {i: [o for o in s if since <= o.t <= now_t] for i, s in observe.watch_observations(db, args.house).items()}
    watch = {i: s for i, s in watch.items() if s}
    # th freshest book 4 each item w raw listings: th last api dump's, or a watch poll if one came after it
    books = {i: s[-1] for i, s in obs.items()}
    for i, s in watch.items():
        if i not in books or s[-1].t > books[i].t:
            books[i] = s[-1]
    # newest wins: a watch poll after th last dump replaces th dump's floor, median nd quantity. listings stay
    # th api's, watch rows r price levels w seller counts, not auctions. every row says where its book came
    # from nd whether thats real-time or th hourly dump
    seen = {i: (snaps[-1][1], "api") for i in now}
    for i, b in books.items():
        if b.source == "watch" and b.t > snaps[-1][1] and b.listings:
            lots = sorted((l.unit_price, l.quantity) for l in b.listings if l.unit_price is not None)
            qty = sum(q for _, q in lots)
            med = next(price for price, acc in zip((p for p, _ in lots), accumulate(q for _, q in lots))
                       if acc * 2 >= qty)
            now[i] = (med, lots[0][0], qty, now[i][3] if i in now else None)
            seen[i] = (b.t, "watch")
    dump_times = [t for _, t in snaps]
    merged = {i: fills.merge(list(fills.api_fills(obs.get(i, []))), list(fills.watch_fills(watch.get(i, []))),
                             fills.watch_spans(watch.get(i, [])), dump_times)
              for i in obs.keys() | watch.keys()}
    recent_since = snaps[max(0, len(snaps) - args.dry_dumps)][1]
    sold, pulled, recent, events, maybe = fills.tally((f for fs in merged.values() for f in fs), recent_since)
    sure = {i: [f for f in fs if f.kind == "sale" and f.confidence == "high"] for i, fs in merged.items()}
    recent_h = (snaps[-1][1] - snaps[max(0, len(snaps) - 1 - args.dry_dumps)][1]) / 3600
    # items r tracked from th first dump they have raw listings in; items added 2 th watchlist mid-window
    # (or never listed) get "-" instead of a fake zero. under an hour of tracking measures nothing yet
    dump_time = dict(snaps)
    marks = ",".join("?" * len(snaps))
    first_seen = dict(db.execute(f"select item_id, min(snapshot_id) from auction where snapshot_id in ({marks}) group by item_id",
                                 [s for s, _ in snaps]))
    # nd watched items add th stretches their polls actually covered. a lone poll covers nothing, nd th gap
    # between th last dump nd th first poll wasnt watched by anyone, so neither stretches th denominator
    covered = defaultdict(list)
    for i, sid in first_seen.items():
        covered[i].append((dump_time[sid], snaps[-1][1]))
    for i, s in watch.items():
        covered[i] += fills.watch_spans(s)
    tracked_h = {i: covered_seconds(spans) / 3600 for i, spans in covered.items() if spans}

    # gear, rods etc cant be listed under 1s (th ah errors), stackables go down 2 1c. at th minimum u cant
    # undercut, so u queue behind every unit already listed there
    last = snaps[-1][0]
    single = {i for (i,) in db.execute("select item_id from price where snapshot_id = ? and commodity = 0", (last,))}
    at_floor = dict(db.execute(
        "select a.item_id, sum(a.quantity) from auction a join price p on p.snapshot_id = a.snapshot_id "
        "and p.item_id = a.item_id where a.snapshot_id = ? and a.unit_price = p.min_unit group by a.item_id", (last,)))

    def sell_odds(rate, need, hours):
        """chance of at least `need` buying sprees b4 a listing of `hours` expires, sprees being poisson at rate/h"""
        mu = rate * hours
        if not mu:
            return 0.0
        return max(0.0, 1 - sum(math.exp(k * math.log(mu) - mu - math.lgamma(k + 1)) for k in range(need)))

    def market(i, stack=1):
        """stack is how many u list at once, a craft's avg yield"""
        n, t, s = now.get(i), then.get(i), sold.get(i)
        hours = tracked_h.get(i, 0)
        units = (s[0] if s else 0) if hours >= 1 else None
        rate = events[i] / hours if units is not None else None
        pinned = n is not None and n[1] <= (100 if i in single else 1)
        ahead = at_floor.get(i, n[2] if n else 0) if pinned else 0
        # each spree eats ~per_spree units off th bottom of th book, so urs go after enough sprees 2 clear
        # th queue ahead nd ur whole stack
        need = math.ceil((ahead + stack) / (units / events[i])) if units else None
        # th deposit only comes back on a sale, so every listing tht expires first loses one. thats geometric
        # in th odds of selling per listing; past args.give_up_days of relisting u'd give up nd vendor it. each
        # listing length trades a cheaper deposit against worse odds of a spree landing b4 it runs out, so
        # take whichever loses least. items w no known vendor price fall back 2 th flat args.deposit guess
        sell = (items.get(i) or (None, None))[1]
        if rate is None:
            deposits = duration = listing_deposit = None
        else:
            options = []
            for h, percent in AUCTION_DURATIONS:
                p = sell_odds(rate, need, h) if need else 0.0
                d = deposit(sell, max(1, round(stack)), percent) if sell is not None else args.deposit
                options.append((round(d * min((1 - p) / p if p else math.inf, args.give_up_days * 24 / h)), h, d))
            deposits, duration, listing_deposit = min(options)
        wait_h = need / rate if rate else None
        step = 100 if i in single else 1
        clearing = clearing_price(sure.get(i, ())) if units is not None else None
        trend = trend_per_h(sure.get(i, ())) if units is not None else None
        # no real market, just sellers undercutting each other: way more pulled nd reposted than bought, or sales
        # tht stopped dead (th window's rate says there shud have been a handful by now) while sellers keep
        # reposting. a quiet few hours on its own is just a quiet few hours
        war = None
        if units is not None:
            churn = pulled.get(i, 0)
            if churn >= args.war_ratio * max(units, 1):
                war = "relisting"
            elif churn > units and hours > recent_h and not recent.get(i) and rate * recent_h >= args.dry_expect:
                war = "dried up"
        return {
            "id": i, "name": (items.get(i) or (None,))[0] or f"item {i}",
            "floor": n and n[1], "median": n and n[0], "qty": n and n[2], "listings": n and n[3],
            "floor_then": t and t[1],
            "sold": units,
            # low-confidence watch sales on top of `sold`, so th site can say "61 (+14?)" instead of guessing
            "sold_maybe": maybe.get(i, 0) if units is not None else None,
            "pulled": pulled.get(i, 0) if units is not None else None,
            "war": war,
            "sold_at": round(s[1] / s[0]) if units else None,
            "clearing": clearing,
            "trend_per_h": trend,
            # wat listing one now shud actually fetch, see realizable()
            "realizable": realizable(n and n[1], step, clearing, trend, wait_h),
            # as th cheapest listing urs sells in th spree tht clears everything queued ahead of it
            "wait_h": wait_h,
            "ahead": ahead,
            "deposit_risk": deposits,
            # wat th deposit_risk assumes: list 4 duration_h at listing_deposit each (deposit_known: from th
            # formula, not th flat guess)
            "duration_h": duration,
            "listing_deposit": listing_deposit,
            "deposit_known": sell is not None,
            "vendor": (items.get(i) or (None, None))[1],
            "as_of": seen.get(i, (None,))[0],
            "source": seen.get(i, (None, None))[1],
            "live": i in seen and now_t - seen[i][0] <= LIVE_S,
        }


    def buy_cost(i, q):
        return walk_book(books[i].listings if i in books else (), q, now[i][0])

    crafts = craft_tables(db, now, items, market, buy_cost)

    gather = {k: [market(i) for i in ids if i in now] for k, ids in GATHERED.items()}

    flips, vendor = spreads(args, db, snaps, now, bw, items, book)

    return {
        "house": args.house, "dump": snaps[-1][1], "first_dump": snaps[0][1], "dumps": len(snaps),
        "hours": round((snaps[-1][1] - snaps[0][1]) / 3600), "crafts": crafts, "gather": gather, "flips": flips, "vendor": vendor,
    }
