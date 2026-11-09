#!/usr/bin/env python3
"""WoW: Forever auction house tracker.

  forever-ah scrape   snapshot every house as per-item aggregates, plus raw auctions 4 watched items
  forever-ah recipes  cache profession recipes + item vendor prices from th static api
  forever-ah analyze  craft profitability 4 one house from th latest snapshot

creds: BNET_CLIENT_ID / BNET_CLIENT_SECRET, or ~/.secrets/battle-net-client-{id,secret}
"""
import argparse
import base64
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

SCHEMA = """
create table if not exists snapshot (
  id integer primary key,
  ts integer not null,
  region text not null,
  house_id integer not null,
  house_name text not null
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
"""


class Client:
    """Blizzard API client, throttled well under th 100 req/s / 36k req/h limits."""

    def __init__(self, region, client_id, client_secret, min_interval=0.2, retries=5):
        self.region = region
        self.min_interval = min_interval
        self.retries = retries
        self.last = 0.0
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
            wait = self.last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code != 429 and e.code < 500:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 2 ** attempt))
        raise RuntimeError(f"gave up on {path} after {self.retries} attempts")


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
    # every bs/mining reagent nd output; empty until `recipes` has run once
    watched = {i for (i,) in db.execute("select item_id from reagent union select crafted_item_id from recipe")}

    # every ruleset lists th same houses w identical data, so walk only th first one
    ruleset = api.get("/data/wow/ruleset/index")["rulesets"][0]["id"]
    houses = api.get(f"/data/wow/ruleset/{ruleset}/auctions/")["auctions"]

    ts = int(time.time())
    for h in houses:
        base = f"/data/wow/ruleset/{ruleset}/auctions/{h['id']}"
        regular = (api.get(base) or {}).get("auctions") or []
        commodities = (api.get(base + "/commodities") or {}).get("auctions") or []
        cur = db.execute(
            "insert into snapshot (ts, region, house_id, house_name) values (?, ?, ?, ?)",
            (ts, args.region, h["id"], h["name"]),
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


def recipes(args, db):
    api = Client(args.region, *creds())
    item_ids = set()
    for prof in args.profession:
        for tier in api.get(f"/data/wow/profession/{prof}", "static")["skill_tiers"]:
            st = api.get(f"/data/wow/profession/{prof}/skill-tier/{tier['id']}", "static")
            for cat in st.get("categories", []):
                for r in cat.get("recipes", []):
                    rec = api.get(f"/data/wow/recipe/{r['id']}", "static")
                    if rec is None:
                        continue
                    crafted = rec.get("crafted_item") or rec.get("alliance_crafted_item")
                    qty = rec.get("crafted_quantity", {})
                    db.execute(
                        "insert or replace into recipe values (?, ?, ?, ?, ?, ?, ?)",
                        (rec["id"], prof, cat["name"], rec["name"], crafted and crafted["id"],
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
            print(f"profession {prof} tier {tier['name']}: {n} recipes")

    known = {i for (i,) in db.execute("select id from item where found = 1")}
    for iid in sorted(item_ids - known):
        it = api.get(f"/data/wow/item/{iid}", "static")
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("FOREVER_AH_DB", "forever-ah.sqlite"))
    ap.add_argument("--region", default="us")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scrape")
    # 111 is normal alliance
    sp.add_argument("--track-house", type=int, action="append", help="houses 2 keep raw auctions 4 (default 111)")
    rp = sub.add_parser("recipes")
    rp.add_argument("--profession", type=int, action="append", help="profession ids (default 164 blacksmithing, 186 mining)")
    an = sub.add_parser("analyze")
    an.add_argument("--house", type=int, default=111)
    an.add_argument("--profession", type=int, default=164)
    an.add_argument("--min-auctions", type=int, default=5, help="ignore crafted items w fewer listings")
    an.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    if args.cmd == "scrape":
        args.track_house = args.track_house or [111]
    if args.cmd == "recipes":
        args.profession = args.profession or [164, 186]

    # scrape nd recipes share th db on a timer, so wait out th other's write lock instead of dying
    db = sqlite3.connect(args.db, timeout=60)
    db.executescript(SCHEMA)
    {"scrape": scrape, "recipes": recipes, "analyze": analyze}[args.cmd](args, db)


if __name__ == "__main__":
    main()
