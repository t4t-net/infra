#!/usr/bin/env python3
"""WoW: Forever auction house tracker.

  forever-ah scrape   snapshot every house as per-item aggregates, plus raw auctions 4 watched items
  forever-ah recipes  cache profession recipes + item vendor prices from th static api
  forever-ah analyze  craft profitability 4 one house from th latest snapshot
  forever-ah export   write th gold meta site + a fresh data.json

creds: BNET_CLIENT_ID / BNET_CLIENT_SECRET, or ~/.secrets/battle-net-client-{id,secret}
"""
import argparse
import base64
import email.utils
import json
import os
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCHEMA = """
create table if not exists snapshot (
  id integer primary key,
  ts integer not null,
  region text not null,
  house_id integer not null,
  house_name text not null,
  data_ts integer                 -- blizz's Last-Modified 4 th house dump, can lag ts by an hour+
);
create table if not exists price (
  snapshot_id integer not null references snapshot(id),
  item_id integer not null,
  commodity integer not null,
  min_unit integer not null,      -- copper
  median_unit integer not null,   -- quantity-weighted, copper
  quantity integer not null,
  auctions integer not null,
  primary key (snapshot_id, item_id, commodity)
);
create index if not exists price_item on price(item_id);

-- raw listings 4 watched items in tracked houses. an auction id vanishing w time left on it
-- between snapshots means it (almost always) sold
create table if not exists auction (
  snapshot_id integer not null references snapshot(id),
  auction_id integer not null,
  item_id integer not null,
  unit_price integer,             -- null 4 bid-only
  quantity integer not null,
  time_left text not null,
  primary key (snapshot_id, auction_id)
);
create index if not exists auction_item on auction(item_id);

create table if not exists recipe (
  id integer primary key,
  profession_id integer not null,
  category text not null,
  name text not null,
  crafted_item_id integer,        -- null 4 enchants etc
  crafted_min integer,
  crafted_max integer
);
create table if not exists reagent (
  recipe_id integer not null references recipe(id),
  item_id integer not null,
  quantity integer not null,
  primary key (recipe_id, item_id)
);
create table if not exists item (
  id integer primary key,
  name text,
  sell_price integer,             -- wat a vendor pays u, copper
  purchase_price integer,         -- wat a vendor charges, copper (set even 4 items no vendor sells)
  found integer not null          -- 0 when static-forever 404s
);
create table if not exists item_quality (
  id integer primary key,
  quality text not null           -- poor/common/uncommon/rare/epic/legendary, 4 th site's name colors
);
"""

PROFESSIONS = {164: "blacksmithing", 202: "engineering", 197: "tailoring", 165: "leatherworking",
               171: "alchemy", 333: "enchanting", 185: "cooking", 186: "mining"}

# raw mats th site lists 4 gathering, which have no recipes of their own
GATHERED = {
    "mining": [2770, 2840, 2835, 774, 818, 1210, 2771, 3576, 2836, 1206, 1705, 2775, 2842, 2772, 3575, 3859, 2838,
               2776, 3577, 3858, 3860, 7912, 7911, 6037, 10620, 12359, 12365, 11370],
    "herbalism": [2447, 765, 2449, 785, 2450, 2453, 2452, 3355, 3369, 3356, 3357, 3818, 3821, 3358, 3819, 4625,
                  8831, 8836, 8838, 8839, 8845, 8846, 13464, 13463, 13465, 13466, 13467, 13468],
    "skinning": [2934, 2318, 783, 2319, 4232, 4234, 4235, 4304, 8169, 8170, 8171, 4461, 5784, 7286, 8154, 8165],
    "cloth": [2589, 2592, 4306, 4338, 14047, 14256],
}

# reagents trade-supply vendors actually sell; blizz sets purchase_price on everything, so it cant tell us
VENDOR_MATS = {"Weak Flux", "Strong Flux", "Coal", "Fine Thread", "Coarse Thread", "Silken Thread", "Heavy Silken Thread",
               "Rune Thread", "Flask of Oil", "Empty Vial", "Leaded Vial", "Crystal Vial", "Imbued Vial", "Salt",
               "Mild Spices", "Hot Spices", "Refreshing Spring Water", "Ice Cold Milk", "Simple Flour", "Gray Dye",
               "Blue Dye", "Red Dye", "Bleach", "Pink Dye", "Black Dye", "Green Dye", "Purple Dye", "Orange Dye",
               "Yellow Dye", "Simple Wood"}


class Client:
    """Blizzard API client, throttled 2 half th 100 req/s limit. th 36k req/h cap is wat bites first:
    a full recipe crawl is ~4k calls, so only back-2-back giant crawls get near it (429s back off)."""

    def __init__(self, region, client_id, client_secret, min_interval=0.02, retries=5):
        self.region = region
        self.min_interval = min_interval
        self.retries = retries
        self.last = 0.0
        self.lock = threading.Lock()
        # of th most recent response, as unix seconds. only meaningful 4 sequential get()s, not get_many
        self.last_modified = None
        req = urllib.request.Request(
            "https://oauth.battle.net/token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            self.token = json.load(r)["access_token"]

    def get(self, path, namespace="dynamic"):
        """GET path in {namespace}-forever-{region}; returns None on 404."""
        url = f"https://{self.region}.api.blizzard.com{path}?" + urllib.parse.urlencode(
            {"namespace": f"{namespace}-forever-{self.region}", "locale": "en_US"}
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        for attempt in range(self.retries):
            # reserve th next free slot under th lock, then sleep outside it so other threads queue up behind
            with self.lock:
                now = time.monotonic()
                slot = max(now, self.last + self.min_interval)
                self.last = slot
            if slot > now:
                time.sleep(slot - now)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    lm = r.headers.get("Last-Modified")
                    self.last_modified = int(email.utils.parsedate_to_datetime(lm).timestamp()) if lm else None
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code != 429 and e.code < 500:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 2 ** attempt))
        raise RuntimeError(f"gave up on {path} after {self.retries} attempts")

    def get_many(self, paths, namespace="dynamic", workers=16):
        """get() each path concurrently, results in th same order. one request at a time is latency-bound
        at ~7/s from psychoboost, so th throttle only actually matters once there r a bunch in flight"""
        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(lambda p: self.get(p, namespace), paths))


def creds():
    if "BNET_CLIENT_ID" in os.environ:
        return os.environ["BNET_CLIENT_ID"], os.environ["BNET_CLIENT_SECRET"]
    secrets = Path("~/.secrets").expanduser()
    return (
        (secrets / "battle-net-client-id").read_text().strip(),
        (secrets / "battle-net-client-secret").read_text().strip(),
    )


def unit_price(a, commodity):
    if commodity:
        return a.get("unit_price")
    return a["buyout"] // a.get("quantity", 1) if a.get("buyout") else None


def aggregate(rows, commodity):
    # item_id -> list of (unit_price, quantity); bid-only auctions have no buyout, skip them
    by_item = defaultdict(list)
    for a in rows:
        unit = unit_price(a, commodity)
        if unit:
            by_item[a["item"]["id"]].append((unit, a.get("quantity", 1)))
    out = []
    for item_id, lots in by_item.items():
        lots.sort()
        total = sum(q for _, q in lots)
        acc, median = 0, lots[-1][0]
        for unit, q in lots:
            acc += q
            if acc * 2 >= total:
                median = unit
                break
        out.append((item_id, int(commodity), lots[0][0], median, total, len(lots)))
    return out


def scrape(args, db):
    api = Client(args.region, *creds())
    # every reagent nd output of th crawled professions; empty until `recipes` has run once
    watched = {i for (i,) in db.execute("select item_id from reagent union select crafted_item_id from recipe")}

    # every ruleset lists th same houses w identical data, so walk only th first one
    ruleset = api.get("/data/wow/ruleset/index")["rulesets"][0]["id"]
    houses = api.get(f"/data/wow/ruleset/{ruleset}/auctions/")["auctions"]

    ts = int(time.time())
    for h in houses:
        base = f"/data/wow/ruleset/{ruleset}/auctions/{h['id']}"
        regular = (api.get(base) or {}).get("auctions") or []
        data_ts = api.last_modified
        commodities = (api.get(base + "/commodities") or {}).get("auctions") or []
        # blizz hasnt republished since last run, a second copy would just look like nothing sold
        prev = db.execute("select max(data_ts) from snapshot where house_id = ?", (h["id"],)).fetchone()[0]
        if data_ts is not None and data_ts == prev:
            print(f"{h['id']:>4} {h['name']:<28} unchanged since {time.strftime('%H:%M', time.localtime(data_ts))}")
            continue
        cur = db.execute(
            "insert into snapshot (ts, region, house_id, house_name, data_ts) values (?, ?, ?, ?, ?)",
            (ts, args.region, h["id"], h["name"], data_ts),
        )
        sid = cur.lastrowid
        db.executemany(
            "insert into price values (?, ?, ?, ?, ?, ?, ?)",
            [(sid, *r) for r in aggregate(regular, False) + aggregate(commodities, True)],
        )
        if h["id"] in args.track_house:
            db.executemany(
                "insert or ignore into auction values (?, ?, ?, ?, ?, ?)",
                [
                    (sid, a["id"], a["item"]["id"], unit_price(a, commodity), a.get("quantity", 1), a["time_left"])
                    for commodity, rows in ((False, regular), (True, commodities))
                    for a in rows
                    if a["item"]["id"] in watched
                ],
            )
        db.commit()
        print(f"{h['id']:>4} {h['name']:<28} {len(regular) + len(commodities):>6} auctions")

    # raw listings r th bulk of th db nd only matter 4 recent sell-through; per-item prices stay forever
    cutoff = ts - args.keep_days * 86400
    gone = db.execute("delete from auction where snapshot_id in (select id from snapshot where ts < ?)", (cutoff,)).rowcount
    db.commit()
    if gone:
        print(f"pruned {gone} raw listings older than {args.keep_days}d")


def recipes(args, db):
    api = Client(args.region, *creds())
    item_ids = set()
    for prof in args.profession:
        # th profession nd tier listings r a few calls; th recipes themselves r th bulk, so those fan out
        listed = []
        for tier in api.get(f"/data/wow/profession/{prof}", "static")["skill_tiers"]:
            st = api.get(f"/data/wow/profession/{prof}/skill-tier/{tier['id']}", "static")
            listed += [(cat["name"], r["id"]) for cat in st.get("categories", []) for r in cat.get("recipes", [])]
        fetched = api.get_many([f"/data/wow/recipe/{rid}" for _, rid in listed], "static")
        for (category, _), rec in zip(listed, fetched):
            if rec is None:
                continue
            crafted = rec.get("crafted_item") or rec.get("alliance_crafted_item")
            qty = rec.get("crafted_quantity", {})
            db.execute(
                "insert or replace into recipe values (?, ?, ?, ?, ?, ?, ?)",
                (rec["id"], prof, category, rec["name"], crafted and crafted["id"],
                 qty.get("minimum", qty.get("value", 1)), qty.get("maximum", qty.get("value", 1))),
            )
            db.execute("delete from reagent where recipe_id = ?", (rec["id"],))
            for rg in rec.get("reagents", []):
                db.execute("insert into reagent values (?, ?, ?)", (rec["id"], rg["reagent"]["id"], rg["quantity"]))
                item_ids.add(rg["reagent"]["id"])
            if crafted:
                item_ids.add(crafted["id"])
        db.commit()
        n = db.execute("select count(*) from recipe where profession_id = ?", (prof,)).fetchone()[0]
        print(f"profession {prof}: {n} recipes", flush=True)

    known = {i for (i,) in db.execute("select id from item where found = 1")}
    todo = sorted(item_ids - known)
    for iid, it in zip(todo, api.get_many([f"/data/wow/item/{i}" for i in todo], "static")):
        if it is None:
            db.execute("insert or replace into item values (?, null, null, null, 0)", (iid,))
        else:
            db.execute("insert or replace into item values (?, ?, ?, ?, 1)", (iid, it["name"], it.get("sell_price"), it.get("purchase_price")))
    db.commit()
    missing = db.execute("select count(*) from item where found = 0").fetchone()[0]
    print(f"items: {len(item_ids)} referenced, {missing} missing from static-forever")


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
    items = {i: (name, buy) for i, name, buy in db.execute("select id, name, purchase_price from item")}

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


def market_data(args, db):
    """Everything th site shows, from th dumps in th last args.hours."""
    since = int(time.time()) - args.hours * 3600
    # one snapshot per distinct dump; scrapes from before Last-Modified tracking can repeat a dump
    snaps, seen = [], set()
    for sid, ts, dts in db.execute(
            "select id, ts, data_ts from snapshot where house_id = ? and ts >= ? order by ts", (args.house, since)):
        if (dts or ts) not in seen:
            seen.add(dts or ts)
            snaps.append((sid, dts or ts))
    if not snaps:
        raise SystemExit(f"no snapshots of house {args.house} in th last {args.hours}h")
    bw_last = db.execute("select id from snapshot where house_id = ? order by ts desc limit 1", (args.blackwater,)).fetchone()

    def book(sid):
        return {i: (med, mn, q, n) for i, med, mn, q, n in db.execute(
            "select item_id, median_unit, min_unit, quantity, auctions from price where snapshot_id = ? order by quantity", (sid,))}

    now, then = book(snaps[-1][0]), book(snaps[0][0])
    bw = book(bw_last[0]) if bw_last else {}
    items = {i: (n, s, b) for i, n, s, b in db.execute("select id, name, sell_price, purchase_price from item")}

    # sales: listings tht vanished w time left, at or under th next dump's floor (buyers take th cheapest first,
    # so a pricier one tht vanished was a cancel or a repost)
    sold = defaultdict(lambda: [0, 0])
    for (a, _), (b, _) in zip(snaps, snaps[1:]):
        after = dict(db.execute("select auction_id, quantity from auction where snapshot_id = ?", (b,)))
        floor = dict(db.execute("select item_id, min(min_unit) from price where snapshot_id = ? group by item_id", (b,)))
        for aid, iid, price, q, tl in db.execute(
                "select auction_id, item_id, unit_price, quantity, time_left from auction where snapshot_id = ?", (a,)):
            if price is None or tl == "SHORT" or (iid in floor and price > floor[iid]):
                continue
            gone = q - after.get(aid, 0)
            if gone > 0:
                sold[iid][0] += gone
                sold[iid][1] += gone * price
    # anything w raw listings in th window is tracked; others get "-" instead of a fake zero
    marks = ",".join("?" * len(snaps))
    watched = {i for (i,) in db.execute(f"select distinct item_id from auction where snapshot_id in ({marks})", [s for s, _ in snaps])}

    def market(i):
        n, t, s = now.get(i), then.get(i), sold.get(i)
        return {
            "id": i, "name": (items.get(i) or (None,))[0] or f"item {i}",
            "floor": n and n[1], "median": n and n[0], "qty": n and n[2], "listings": n and n[3],
            "floor_then": t and t[1],
            "sold": (s[0] if s else 0) if i in watched else None,
            "vendor": (items.get(i) or (None, None))[1],
        }

    crafts = {}
    for pid, pname in PROFESSIONS.items():
        rows = []
        for rid, rname, out, cmin, cmax in db.execute(
                "select id, name, crafted_item_id, crafted_min, crafted_max from recipe where profession_id = ? and crafted_item_id is not null", (pid,)):
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
                    cost += now[i][0] * q
                    mats.append({"id": i, "name": nm or f"item {i}", "qty": q})
                else:
                    ok = False
            if not ok or not cost:
                continue
            per = (cmin + cmax) / 2
            rev = int(o[1] * per * 0.95)
            rows.append({"recipe": rname, "makes": per, "cost": cost, "revenue": rev, "profit": rev - cost,
                         "mats": mats, "out": market(out)})
        rows.sort(key=lambda r: -r["profit"])
        crafts[pname] = {
            "count": db.execute("select count(*) from recipe where profession_id = ?", (pid,)).fetchone()[0],
            "priced": len(rows),
            "top": [r for r in rows if r["profit"] > 0][:14],
            "starters": sorted([r for r in rows if r["profit"] > 0 and r["cost"] <= 2500], key=lambda r: -r["profit"])[:8],
            "losers": len([r for r in rows if r["profit"] <= 0]),
        }

    gather = {k: [market(i) for i in ids if i in now] for k, ids in GATHERED.items()}

    # buy in th quiet neutral house, sell here; 15% neutral cut is classic's, unverified 4 forever
    flips = []
    for i in now.keys() & bw.keys():
        buy, sell = bw[i][1], now[i][1] * 0.95
        if now[i][3] >= 8 and bw[i][3] >= 2 and sell > buy * 1.5 and sell - buy >= 2000:
            flips.append({"id": i, "name": (items.get(i) or (None,))[0] or f"item {i}", "buy": buy, "buy_listings": bw[i][3],
                          "sell": now[i][1], "sell_listings": now[i][3], "profit": int(sell - buy)})
    flips.sort(key=lambda f: -f["profit"])

    # names nd qualities 4 anything shown tht th recipe crawl didnt cover, cached so this only costs calls once
    shown = [m for ms in gather.values() for m in ms] + flips
    shown_ids = {m["id"] for m in shown}
    for v in crafts.values():
        for r in v["top"] + v["starters"]:
            shown_ids.add(r["out"]["id"])
            shown_ids.update(m["id"] for m in r["mats"])
    quality = dict(db.execute("select id, quality from item_quality"))
    todo = sorted(shown_ids - quality.keys())
    names = {}
    if todo:
        api = Client(args.region, *creds())
        for i, it in zip(todo, api.get_many([f"/data/wow/item/{i}" for i in todo], "static")):
            quality[i] = it["quality"]["type"].lower() if it and it.get("quality") else "common"
            if it:
                names[i] = it["name"]
            db.execute("insert or replace into item_quality values (?, ?)", (i, quality[i]))
        db.commit()
    for m in shown:
        if m["name"].startswith("item ") and m["id"] in names:
            m["name"] = names[m["id"]]
    flips = [f for f in flips if not f["name"].startswith("item ")][:10]

    return {
        "house": args.house, "dump": snaps[-1][1], "first_dump": snaps[0][1], "dumps": len(snaps),
        "hours": round((snaps[-1][1] - snaps[0][1]) / 3600), "crafts": crafts, "gather": gather, "flips": flips,
        "quality": {i: quality[i] for i in shown_ids},
    }


def export(args, db):
    """Write th built site plus a fresh data.json 2 args.out, swapped in whole so it never serves half a site."""
    data = market_data(args, db)
    out = Path(args.out)
    new, old = out.with_name(out.name + ".new"), out.with_name(out.name + ".old")
    shutil.rmtree(new, ignore_errors=True)
    # copyfile, not copytree: th nix store copies r read-only nd th next export has 2 replace them
    for src in Path(args.site).rglob("*"):
        dst = new / src.relative_to(args.site)
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    (new / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    shutil.rmtree(old, ignore_errors=True)
    if out.exists():
        out.rename(old)
    new.rename(out)
    shutil.rmtree(old, ignore_errors=True)
    print(f"exported {data['dumps']} dumps over {data['hours']}h 2 {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("FOREVER_AH_DB", "forever-ah.sqlite"))
    ap.add_argument("--region", default="us")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scrape")
    # 111 is normal alliance
    sp.add_argument("--track-house", type=int, action="append", help="houses 2 keep raw auctions 4 (default 111)")
    sp.add_argument("--keep-days", type=int, default=7, help="prune raw auctions older than this")
    rp = sub.add_parser("recipes")
    rp.add_argument("--profession", type=int, action="append", help="profession ids (default: all crafting professions)")
    ex = sub.add_parser("export")
    ex.add_argument("--house", type=int, default=111)
    ex.add_argument("--blackwater", type=int, default=117, help="th neutral house alliance can also reach")
    ex.add_argument("--hours", type=int, default=24, help="trend nd sales window")
    ex.add_argument("--site", required=True, help="built forever-ah-site directory")
    ex.add_argument("--out", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("--house", type=int, default=111)
    an.add_argument("--profession", type=int, default=164)
    an.add_argument("--min-auctions", type=int, default=5, help="ignore crafted items w fewer listings")
    an.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    if args.cmd == "scrape":
        args.track_house = args.track_house or [111]
    if args.cmd == "recipes":
        args.profession = args.profession or list(PROFESSIONS)

    # scrape nd recipes share th db on a timer, so wait out th other's write lock instead of dying
    db = sqlite3.connect(args.db, timeout=60)
    db.executescript(SCHEMA)
    if "data_ts" not in {c[1] for c in db.execute("pragma table_info(snapshot)")}:
        db.execute("alter table snapshot add column data_ts integer")
    {"scrape": scrape, "recipes": recipes, "analyze": analyze, "export": export}[args.cmd](args, db)


if __name__ == "__main__":
    main()
