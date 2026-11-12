"""th hourly api scrape: every house as per-item aggregates, raw listings 4 watched items, vendor price backfill."""
import time
from collections import defaultdict


from api import Client, creds


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

    backfill_items(args, db, ts)

    # raw listings r th bulk of th db nd only matter 4 recent sell-through; per-item prices stay forever
    cutoff = ts - args.keep_days * 86400
    gone = db.execute("delete from auction where snapshot_id in (select id from snapshot where ts < ?)", (cutoff,)).rowcount
    db.commit()
    if gone:
        print(f"pruned {gone} raw listings older than {args.keep_days}d")


def backfill_items(args, db, ts):
    """Vendor prices 4 everything in th scrape at ts, not just recipe items, so export can spot listings under
    wat a vendor pays. th first run is ~5k items; after tht its th handful tht showed up new"""
    todo = [i for (i,) in db.execute("select distinct item_id from price where snapshot_id in "
                                     "(select id from snapshot where ts = ?) and item_id not in (select id from item)", (ts,))]
    if not todo:
        return
    api = Client(args.region, *creds())
    for iid, it in zip(todo, api.get_many([f"/data/wow/item/{i}" for i in todo], "static")):
        if it is None:
            db.execute("insert or replace into item values (?, null, null, null, 0)", (iid,))
        else:
            db.execute("insert or replace into item values (?, ?, ?, ?, 1)", (iid, it["name"], it.get("sell_price"), it.get("purchase_price")))
    db.commit()
    print(f"fetched {len(todo)} new items")
