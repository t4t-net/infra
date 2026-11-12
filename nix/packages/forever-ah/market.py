"""th market model behind th site. see MARKET.md 4 th rebuild this is waiting on."""
import math
import time
from collections import defaultdict


import fills
import observe
from api import Client, creds
from game import AUCTION_DURATIONS, GATHERED, PROFESSIONS, VENDOR_MATS, deposit


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
    dump_times = [t for _, t in snaps]
    merged = (f for i in obs.keys() | watch.keys()
              for f in fills.merge(list(fills.api_fills(obs.get(i, []))), list(fills.watch_fills(watch.get(i, []))),
                                   fills.watch_spans(watch.get(i, [])), dump_times))
    recent_since = snaps[max(0, len(snaps) - args.dry_dumps)][1]
    sold, pulled, recent, events, maybe = fills.tally(merged, recent_since)
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
            # as th cheapest listing urs sells in th spree tht clears everything queued ahead of it
            "wait_h": need / rate if rate else None,
            "ahead": ahead,
            "deposit_risk": deposits,
            # wat th deposit_risk assumes: list 4 duration_h at listing_deposit each (deposit_known: from th
            # formula, not th flat guess)
            "duration_h": duration,
            "listing_deposit": listing_deposit,
            "deposit_known": sell is not None,
            "vendor": (items.get(i) or (None, None))[1],
        }

    # th freshest book 4 each item w raw listings: th last api dump's, or a watch poll if one came after it
    books = {i: s[-1] for i, s in obs.items()}
    for i, s in watch.items():
        if i not in books or s[-1].t > books[i].t:
            books[i] = s[-1]

    def buy_cost(i, q):
        return walk_book(books[i].listings if i in books else (), q, now[i][0])

    # farming it urself: gathered mats r free, vendor mats cost wat th vendor charges, nd intermediates (bars,
    # bolts, leather) r made from their own mats if this profession or mining smelting can. anything else
    # (dust, drops, other professions' parts) still gets bought at median
    gathered = {i for ids in GATHERED.values() for i in ids}
    makers = defaultdict(list)  # item -> [(profession, recipe id, makes per craft)]
    for rid, pid, out, cmin, cmax in db.execute(
            "select id, profession_id, crafted_item_id, crafted_min, crafted_max from recipe where crafted_item_id is not null"):
        makers[out].append((pid, rid, (cmin + cmax) / 2))
    reagents = defaultdict(list)
    for rid, i, q in db.execute("select recipe_id, item_id, quantity from reagent"):
        reagents[rid].append((i, q))

    def farmed(i, prof, busy=frozenset(), q=1):
        """(copper, {(item, source): qty}) per one of item i when getting q of them, or None if theres no way"""
        nm, _, buy = items.get(i, (None, None, None))
        if nm in VENDOR_MATS and buy:
            return buy, {(i, "vendor"): 1}
        best = None
        for pid, rid, per in makers.get(i, []):
            # leather etc drop as-is, only bars get made (else heavy leather turns into 17k ruined scraps lol)
            if pid not in ((186,) if i in gathered else (prof, 186)) or rid in busy:
                continue
            got = farm_recipe(rid, prof, busy | {rid}, q / per)
            if got and (best is None or got[0] / per < best[0]):
                best = (got[0] / per, {k: q / per for k, q in got[1].items()})
        if best and any(src == "farm" for _, src in best[1]):
            return best
        # GATHERED has bars in it 4 th mining page, so this comes after th smelt check
        if i in gathered:
            return 0, {(i, "farm"): 1}
        if i in now:
            return buy_cost(i, q) / q, {(i, "ah"): 1}
        return best

    def farm_recipe(rid, prof, busy=frozenset(), times=1):
        """(copper, {(item, source): qty}) per craft when crafting it `times` times"""
        cost, need = 0, defaultdict(float)
        for i, q in reagents[rid]:
            got = farmed(i, prof, busy, q * times)
            if got is None:
                return None
            cost += got[0] * q
            for k, n in got[1].items():
                need[k] += n * q
        return cost, need

    crafts = {}
    for pid, pname in PROFESSIONS.items():
        rows = []
        for rid, rname, out, cmin, cmax, spell in db.execute(
                "select id, name, crafted_item_id, crafted_min, crafted_max, spell_id from recipe "
                "where profession_id = ? and crafted_item_id is not null", (pid,)):
            o = now.get(out)
            if not o or o[3] < 5:
                continue
            cost, ok, mats = 0, True, []
            for i, q in db.execute("select item_id, quantity from reagent where recipe_id = ?", (rid,)):
                nm, _, buy = items.get(i, (None, None, None))
                if nm in VENDOR_MATS and buy:
                    cost += buy * q
                    mats.append({"id": i, "name": nm, "qty": q, "vendor": True})
                elif i in now:
                    cost += buy_cost(i, q)
                    mats.append({"id": i, "name": nm or f"item {i}", "qty": q})
                else:
                    ok = False
            if not ok or not cost:
                continue
            per = (cmin + cmax) / 2
            m = market(out, per)
            # th sales rate was earned at wat things actually sold 4, so never price above tht. a reseller who
            # buys out th floor nd relists at 4x right b4 a dump would otherwise turn a loser into a top craft
            rev = int(min(o[1], m["sold_at"] or o[1]) * per * 0.95)
            profit = rev - cost - (m["deposit_risk"] or 0)
            row = {"recipe": rname, "spell": spell, "makes": per, "cost": cost, "revenue": rev, "profit": profit,
                   "mats": mats, "out": m}
            f = farm_recipe(rid, pid)
            # only worth its own row when some of it is actually farmed, otherwise its just th ah number again
            if f and any(src == "farm" for _, src in f[1]):
                row["farm"] = {
                    "cost": round(f[0]), "profit": round(rev - f[0] - (m["deposit_risk"] or 0)),
                    "mats": [{"id": i, "name": (items.get(i) or (None,))[0] or f"item {i}", "qty": round(q, 2) if q % 1 else int(q), "src": src}
                             for (i, src), q in sorted(f[1].items(), key=lambda kv: kv[0][1] != "farm")],
                }
            rows.append(row)
        wars = len([r for r in rows if r["out"]["war"]])
        rows = [r for r in rows if not r["out"]["war"]]
        rows.sort(key=lambda r: -r["profit"])
        farm = sorted([r for r in rows if "farm" in r and r["farm"]["profit"] > 0], key=lambda r: -r["farm"]["profit"])
        crafts[pname] = {
            "count": db.execute("select count(*) from recipe where profession_id = ?", (pid,)).fetchone()[0],
            "priced": len(rows),
            "top": [r for r in rows if r["profit"] > 0][:14],
            "starters": sorted([r for r in rows if r["profit"] > 0 and r["cost"] <= 2500], key=lambda r: -r["profit"])[:8],
            "farmed": farm[:14],
            "losers": len([r for r in rows if r["profit"] <= 0]),
            "wars": wars,
        }

    gather = {k: [market(i) for i in ids if i in now] for k, ids in GATHERED.items()}

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

    # names nd qualities 4 anything shown tht th recipe crawl didnt cover, cached so this only costs calls once
    shown = [m for ms in gather.values() for m in ms] + flips + vendor
    shown_ids = {m["id"] for m in shown}
    for v in crafts.values():
        for r in v["top"] + v["starters"] + v["farmed"]:
            shown_ids.add(r["out"]["id"])
            shown_ids.update(m["id"] for m in r["mats"] + r.get("farm", {}).get("mats", []))
    quality = dict(db.execute("select id, quality from item_quality"))
    named = {i for (i,) in db.execute("select id from item where name is not null")}
    # anything shown w/o a cached quality or name (flips can be any item, not just recipe mats)
    todo = sorted((shown_ids - quality.keys()) | (shown_ids - named))
    if todo:
        api = Client(args.region, *creds())
        for i, it in zip(todo, api.get_many([f"/data/wow/item/{i}" for i in todo], "static")):
            quality[i] = it["quality"]["type"].lower() if it and it.get("quality") else "common"
            db.execute("insert or replace into item_quality values (?, ?)", (i, quality[i]))
            if it:
                db.execute("insert into item values (?, ?, ?, ?, 1) on conflict(id) do update set name = excluded.name",
                           (i, it["name"], it.get("sell_price"), it.get("purchase_price")))
        db.commit()
        names = dict(db.execute("select id, name from item where name is not null"))
        for m in shown:
            if m["name"].startswith("item ") and m["id"] in names:
                m["name"] = names[m["id"]]
    flips = [f for f in flips if not f["name"].startswith("item ")][:10]

    return {
        "house": args.house, "dump": snaps[-1][1], "first_dump": snaps[0][1], "dumps": len(snaps),
        "hours": round((snaps[-1][1] - snaps[0][1]) / 3600), "crafts": crafts, "gather": gather, "flips": flips, "vendor": vendor,
        "quality": {i: quality[i] for i in shown_ids},
    }
