#!/usr/bin/env python3
"""WoW: Forever auction house tracker.

  forever-ah scrape   snapshot every house as per-item aggregates, plus raw auctions 4 watched items
  forever-ah recipes  cache profession recipes + item vendor prices from th static api
  forever-ah quests   cache quests: questie's levels/givers/chains + th api's rewards
  forever-ah analyze  craft profitability 4 one house from th latest snapshot
  forever-ah export   write a fresh data.json 4 th gold meta site
  forever-ah alert    post newly opened flips 2 discord

creds: BNET_CLIENT_ID / BNET_CLIENT_SECRET, or ~/.secrets/battle-net-client-{id,secret}
"""
import argparse
import base64
import email.utils
import json
import math
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import questie
import tact
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
create table if not exists quest (
  id integer primary key,
  name text not null,
  zone integer,                   -- AreaTable id; negative = QuestSort (class/profession quests)
  zone_name text,
  faction text,                   -- ALLIANCE, HORDE or null 4 both
  req_level integer,
  level integer,
  type text,                      -- elite, dungeon, ...
  objectives text,
  starts text,                    -- json [{name, zone, x, y}], from questie's npc/object spawns
  ends text,
  pre_single text,                -- json [quest ids], any one of these first
  pre_group text,                 -- json [quest ids], all of these first
  next_in_chain integer,
  breadcrumb_for integer,
  repeatable integer not null,
  xp integer,
  money integer,                  -- copper
  reward_choice text,             -- json [item ids], pick one
  reward_fixed text,              -- json [item ids], always given
  reputations text                -- json [[faction name, value]]
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
                "insert or replace into recipe (id, profession_id, category, name, crafted_item_id, crafted_min, crafted_max) "
                "values (?, ?, ?, ?, ?, ?, ?)",
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
    print(f"items: {len(item_ids)} referenced, {missing} missing from static-forever", flush=True)
    link_spells(args, db)


# th api's recipe id is th client's SkillLineAbility row id, nd only tht table knows th spell
SKILL_LINE_ABILITY = 1266278  # FileDataID


def link_spells(args, db):
    """Fill each recipe's spell id nd skill ranges from forever's SkillLineAbility.db2, read off blizzard's CDN."""
    st = tact.Storage(args.product, args.cache)
    rows = tact.read_wdc5(st.files([SKILL_LINE_ABILITY])[SKILL_LINE_ABILITY],
                          tact.http(tact.DBD.format(table="SkillLineAbility")).decode())
    sla = {r["ID"]: r for r in rows}
    hit = 0
    for rid, prof in db.execute("select id, profession_id from recipe").fetchall():
        r = sla.get(rid)
        if r and r["SkillLine"] == prof:
            db.execute("update recipe set spell_id = ?, learn_skill = ?, yellow_skill = ?, grey_skill = ? where id = ?",
                       (r["Spell"], r["MinSkillLineRank"], r["TrivialSkillLineRankLow"], r["TrivialSkillLineRankHigh"], rid))
            hit += 1
    db.commit()
    total = db.execute("select count(*) from recipe").fetchone()[0]
    print(f"client build {st.cdn.build}: {hit}/{total} recipes linked 2 their spell", flush=True)


ALLIANCE_RACES, HORDE_RACES = 1 | 4 | 8 | 64, 2 | 16 | 32 | 128  # human dwarf nelf gnome / orc undead tauren troll


def quests(args, db):
    """Questie's levels, givers nd chains + th api's rewards, merged per quest."""
    api = Client(args.region, *creds())
    qdb, npcs, objs = questie.load("Quest"), questie.load("Npc"), questie.load("Object")
    print(f"questie: {len(qdb)} quests, {len(npcs)} npcs, {len(objs)} objects", flush=True)

    # th api lists quests by zone nd by category; together tht's every quest it knows
    areas = {a["id"]: a["name"] for a in api.get("/data/wow/quest/area/index", "static")["areas"]}
    cats = {c["id"]: c["name"] for c in api.get("/data/wow/quest/category/index", "static")["categories"]}
    lists = api.get_many([f"/data/wow/quest/area/{a}" for a in areas] + [f"/data/wow/quest/category/{c}" for c in cats], "static")
    ids = sorted({q["id"] for l in lists if l for q in l.get("quests", [])} | set(qdb))
    details = dict(zip(ids, api.get_many([f"/data/wow/quest/{i}" for i in ids], "static")))
    print(f"api: {sum(1 for d in details.values() if d)} of {len(ids)} quests", flush=True)

    def where(starts, ends=False):
        """questie's startedBy/finishedBy -> [{name, zone, x, y}] from th first spawn of each npc/object"""
        out = []
        for kind, table, keys in ((0, npcs, questie.NPC), (1, objs, questie.OBJECT)):
            for gid in (starts[kind] if starts and kind < len(starts) and starts[kind] else []):
                row = table.get(gid)
                if not row:
                    continue
                spawns = questie.field(row, keys, "spawns") or {}
                zone, pts = next(iter(spawns.items()), (questie.field(row, keys, "zoneID"), [None]))
                pt = pts[0] if pts else None
                out.append({"name": questie.field(row, keys, "name"), "zone": areas.get(zone, zone),
                            "x": pt and pt[0], "y": pt and pt[1]})
        return out

    reward_items = set()
    db.execute("delete from quest")
    for i in ids:
        row, d = qdb.get(i), details.get(i) or {}
        if not row and not d:
            continue
        f = (lambda k: questie.field(row, questie.QUEST, k)) if row else (lambda k: None)
        zone = f("zoneOrSort") or (d.get("area") or {}).get("id")
        zone_name = areas.get(zone) or cats.get(-zone if zone and zone < 0 else zone) or (d.get("area") or {}).get("name")
        faction = ((d.get("requirements") or {}).get("faction") or {}).get("type")
        races = (f("requiredRaces") or 0) % (1 << 32)
        if not faction and races:
            a, h = races & ALLIANCE_RACES, races & HORDE_RACES
            faction = "ALLIANCE" if a and not h else "HORDE" if h and not a else None
        rw = d.get("rewards") or {}
        items = rw.get("items") or {}
        choice = [x["item"]["id"] for x in items.get("choice_of", [])]
        fixed = [x["item"]["id"] for x in items.get("items", [])] if isinstance(items, dict) else []
        reward_items.update(choice + fixed)
        db.execute(
            "insert into quest values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (i, d.get("title") or f("name"), zone, zone_name, faction, f("requiredLevel"), f("questLevel"),
             (d.get("type") or {}).get("name"), " ".join(f("objectivesText") or []) or None,
             json.dumps(where(f("startedBy"))), json.dumps(where(f("finishedBy"))),
             json.dumps(f("preQuestSingle") or []), json.dumps(f("preQuestGroup") or []),
             f("nextQuestInChain"), f("breadcrumbForQuestId"), int(bool((f("specialFlags") or 0) & 1)),
             rw.get("experience"), (rw.get("money") or {}).get("value"), json.dumps(choice), json.dumps(fixed),
             json.dumps([[r["reward"]["name"], r["value"]] for r in rw.get("reputations", [])])))
    db.commit()

    # reward items get names, vendor prices nd qualities now, so th hourly export never has 2 fetch them
    have = {i for (i,) in db.execute("select id from item where name is not null")} & \
           {i for (i,) in db.execute("select id from item_quality")}
    todo = sorted(reward_items - have)
    for i, it in zip(todo, api.get_many([f"/data/wow/item/{i}" for i in todo], "static")):
        if not it:
            continue
        db.execute("insert into item values (?, ?, ?, ?, 1) on conflict(id) do update set name = excluded.name, "
                   "sell_price = excluded.sell_price, purchase_price = excluded.purchase_price",
                   (i, it["name"], it.get("sell_price"), it.get("purchase_price")))
        db.execute("insert or replace into item_quality values (?, ?)", (i, it["quality"]["type"].lower()))
    db.commit()
    n = db.execute("select count(*), count(level), count(xp) from quest").fetchone()
    print(f"stored {n[0]} quests ({n[1]} w a level, {n[2]} w rewards), {len(todo)} reward items looked up", flush=True)


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

    # sales: listings tht vanished w time left. buyers take th cheapest first, so one tht vanished while a cheaper
    # listing from th same dump is still up was pulled (cancelled or reposted), not bought. th next dump's floor
    # isnt good enough 4 this: fresh undercuts land below it nd turned real sales on busy bars into "cancels"
    sold = defaultdict(lambda: [0, 0])
    pulled = defaultdict(int)
    recent = defaultdict(int)  # units sold in th last args.dry_dumps dumps
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
            if n >= len(snaps) - 1 - args.dry_dumps:
                recent[iid] += gone
        for iid in bought:
            events[iid] += 1
    recent_h = (snaps[-1][1] - snaps[max(0, len(snaps) - 1 - args.dry_dumps)][1]) / 3600
    # items r tracked from th first dump they have raw listings in; items added 2 th watchlist mid-window
    # (or never listed) get "-" instead of a fake zero. under an hour of tracking measures nothing yet
    dump_time = dict(snaps)
    marks = ",".join("?" * len(snaps))
    first_seen = dict(db.execute(f"select item_id, min(snapshot_id) from auction where snapshot_id in ({marks}) group by item_id",
                                 [s for s, _ in snaps]))
    tracked_h = {i: (snaps[-1][1] - dump_time[sid]) / 3600 for i, sid in first_seen.items()}

    # gear, rods etc cant be listed under 1s (th ah errors), stackables go down 2 1c. at th minimum u cant
    # undercut, so u queue behind every unit already listed there
    last = snaps[-1][0]
    single = {i for (i,) in db.execute("select item_id from price where snapshot_id = ? and commodity = 0", (last,))}
    at_floor = dict(db.execute(
        "select a.item_id, sum(a.quantity) from auction a join price p on p.snapshot_id = a.snapshot_id "
        "and p.item_id = a.item_id where a.snapshot_id = ? and a.unit_price = p.min_unit group by a.item_id", (last,)))

    def sell_odds(rate, need):
        """chance of at least `need` buying sprees b4 a listing expires, sprees being poisson at rate/h"""
        mu = rate * args.auction_hours
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
        # in th odds of selling per listing; past 2 weeks of relisting u'd give up nd vendor it
        if rate is None:
            deposits = None
        else:
            p = sell_odds(rate, need) if need else 0.0
            deposits = round(args.deposit * min((1 - p) / p if p else math.inf, args.max_relists))
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
            "pulled": pulled.get(i, 0) if units is not None else None,
            "war": war,
            "sold_at": round(s[1] / s[0]) if units else None,
            # as th cheapest listing urs sells in th spree tht clears everything queued ahead of it
            "wait_h": need / rate if rate else None,
            "ahead": ahead,
            "deposit_risk": deposits,
            "vendor": (items.get(i) or (None, None))[1],
        }

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

    def farmed(i, prof, busy=frozenset()):
        """(copper, {(item, source): qty}) 4 one of item i, or None if theres no way 2 get it"""
        nm, _, buy = items.get(i, (None, None, None))
        if nm in VENDOR_MATS and buy:
            return buy, {(i, "vendor"): 1}
        best = None
        for pid, rid, per in makers.get(i, []):
            # leather etc drop as-is, only bars get made (else heavy leather turns into 17k ruined scraps lol)
            if pid not in ((186,) if i in gathered else (prof, 186)) or rid in busy:
                continue
            got = farm_recipe(rid, prof, busy | {rid})
            if got and (best is None or got[0] / per < best[0]):
                best = (got[0] / per, {k: q / per for k, q in got[1].items()})
        if best and any(src == "farm" for _, src in best[1]):
            return best
        # GATHERED has bars in it 4 th mining page, so this comes after th smelt check
        if i in gathered:
            return 0, {(i, "farm"): 1}
        if i in now:
            return now[i][0], {(i, "ah"): 1}
        return best

    def farm_recipe(rid, prof, busy=frozenset()):
        cost, need = 0, defaultdict(float)
        for i, q in reagents[rid]:
            got = farmed(i, prof, busy)
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
                    cost += now[i][0] * q
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

    # names nd qualities 4 anything shown tht th recipe crawl didnt cover, cached so this only costs calls once
    shown = [m for ms in gather.values() for m in ms] + flips
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
        "hours": round((snaps[-1][1] - snaps[0][1]) / 3600), "crafts": crafts, "gather": gather, "flips": flips,
        "quality": {i: quality[i] for i in shown_ids},
    }


def gsc(c):
    """copper as th game prints it, 4 discord"""
    g_, s_, c_ = c // 10000, c // 100 % 100, c % 100
    return " ".join(p for p in (f"{g_}g" if g_ else "", f"{s_}s" if s_ else "", f"{c_}c" if c_ and not g_ else "") if p) or "0c"


def alert(args, db):
    """Post flips tht opened since th last dump 2 discord. th first run only records state."""
    data = json.loads(Path(args.data).read_text())
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if state and state.get("dump") == data["dump"]:
        print("no new dump since last alert")
        return
    was_open = set(state["open"]) if state else None
    flips = data["flips"]
    fresh = [f for f in flips if was_open is not None and f["id"] not in was_open and f["profit"] >= args.min_profit]

    if fresh and not Path(args.webhook_file).exists():
        print(f"{len(fresh)} new flips but no webhook at {args.webhook_file}, skipping")
    elif fresh:
        lines = [f"**{len(fresh)} new flip{'s' if len(fresh) > 1 else ''}** (blackwater -> alliance)"]
        for f in fresh[:10]:
            lines.append(f"[{f['name']}](<https://www.wowhead.com/forever/item={f['id']}>): buy {gsc(f['buy'])} "
                         f"({f['buy_listings']} listed), sell {gsc(f['sell'])} ({f['sell_listings']} listed), "
                         f"**+{gsc(f['profit'])}**, open {f['open']}/{data['dumps']} dumps")
        if args.site:
            lines.append(f"<{args.site}#flips>")
        body = json.dumps({"content": "\n".join(lines)[:2000], "allowed_mentions": {"parse": []}}).encode()
        req = urllib.request.Request(Path(args.webhook_file).read_text().strip(), data=body, headers={
            "Content-Type": "application/json", "User-Agent": "forever-ah/0.1"})
        urllib.request.urlopen(req, timeout=30).close()
        print(f"posted {len(fresh)} new flips")
    else:
        print("first run, recorded state" if was_open is None else "no new flips")

    state_path.write_text(json.dumps({"dump": data["dump"], "open": [f["id"] for f in flips]}))


def quest_data(args, db):
    """Every quest alliance can do, w each reward choice priced: max of th ah floor nd wat a vendor pays."""
    snap = db.execute("select id from snapshot where house_id = ? order by ts desc limit 1", (args.house,)).fetchone()
    floor = dict(db.execute("select item_id, min(min_unit) from price where snapshot_id = ? group by item_id", (snap[0],))) if snap else {}
    items = {i: (n, s) for i, n, s in db.execute("select id, name, sell_price from item")}
    quality = dict(db.execute("select id, quality from item_quality"))

    def reward(i):
        name, sell = items.get(i, (None, None))
        ah = floor.get(i)
        return {"id": i, "name": name or f"item {i}", "q": quality.get(i, "common"), "ah": ah, "vendor": sell,
                "value": max(int((ah or 0) * 0.95), sell or 0)}

    out = []
    for (i, name, zone, req, lvl, typ, starts, pre_single, pre_group, nxt, rep, xp, money, choice, fixed,
         reps) in db.execute(
            "select id, name, zone_name, req_level, level, type, starts, pre_single, pre_group, next_in_chain, "
            "repeatable, xp, money, reward_choice, reward_fixed, reputations from quest "
            "where (faction is null or faction = 'ALLIANCE') and name not like '<%' and zone_name is not null"):
        out.append({"id": i, "name": name, "zone": zone, "req": req, "lvl": lvl, "type": typ, "starts": json.loads(starts or "[]"),
                    "pre": json.loads(pre_single or "[]") + json.loads(pre_group or "[]"), "next": nxt, "rep": bool(rep),
                    "xp": xp, "money": money, "choice": [reward(x) for x in json.loads(choice or "[]")],
                    "fixed": [reward(x) for x in json.loads(fixed or "[]")], "reps": json.loads(reps or "[]")})
    return {"quests": out}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def export(args, db):
    """Write fresh data.json + quests.json 4 th site, renamed into place so th page never fetches half of one."""
    data = market_data(args, db)
    out = Path(args.out)
    write_json(out, data)
    q = quest_data(args, db)
    write_json(out.with_name("quests.json"), q)
    print(f"exported {data['dumps']} dumps over {data['hours']}h nd {len(q['quests'])} quests 2 {out.parent}")


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
    rp.add_argument("--product", default="wowf", help="client product on blizzard's version service (wowf is forever)")
    rp.add_argument("--cache", default=os.environ.get("FOREVER_AH_CDN_CACHE", "cdn-cache"),
                    help="CDN cache; content-addressed, so it only grows across patches")
    sub.add_parser("quests")
    ex = sub.add_parser("export")
    ex.add_argument("--house", type=int, default=111)
    ex.add_argument("--blackwater", type=int, default=117, help="th neutral house alliance can also reach")
    ex.add_argument("--hours", type=int, default=24, help="trend nd sales window")
    ex.add_argument("--deposit", type=int, default=100, help="copper per auction, lost if it expires or gets cancelled")
    ex.add_argument("--auction-hours", type=int, default=24, help="how long a listing runs b4 it expires")
    ex.add_argument("--max-relists", type=int, default=14, help="expired listings b4 u'd give up on selling it")
    ex.add_argument("--war-ratio", type=float, default=3, help="hide crafts w this many units pulled per unit sold")
    ex.add_argument("--dry-dumps", type=int, default=3, help="recent dumps a craft must have sold in...")
    ex.add_argument("--dry-expect", type=float, default=5, help="...when th window's rate expects this many sales in them")
    ex.add_argument("--out", required=True, help="data.json path, next 2 th forever-ah-site files")
    al = sub.add_parser("alert")
    al.add_argument("--data", required=True, help="th data.json export just wrote")
    al.add_argument("--state", required=True, help="where 2 remember wat was already open")
    al.add_argument("--webhook-file", required=True, help="file holding th discord webhook url")
    al.add_argument("--min-profit", type=int, default=5000, help="copper; default 50s")
    al.add_argument("--site", help="site url 2 link at th bottom")
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
    have = {c[1] for c in db.execute("pragma table_info(recipe)")}
    for col in ("spell_id", "learn_skill", "yellow_skill", "grey_skill"):
        if col not in have:
            db.execute(f"alter table recipe add column {col} integer")
    {"scrape": scrape, "recipes": recipes, "quests": quests, "analyze": analyze, "export": export, "alert": alert}[args.cmd](args, db)


if __name__ == "__main__":
    main()
