"""writing th site's data.json + quests.json, nd th discord flip alerts read from them."""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


from api import Client, creds
from market import market_data


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
    items = {i: (n, s) for i, n, s in db.execute("select id, name, sell_price from item_live")}
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


def name_shown(args, db, data):
    """names nd qualities 4 everything th site will show, off th api 4 anything th crawls never cached. lives
    here, not in th model: th model shudnt make network calls, nd only th site cares wat things r called"""
    # names nd qualities 4 anything shown tht th recipe crawl didnt cover, cached so this only costs calls once
    crafts, gather, flips, vendor = data["crafts"], data["gather"], data["flips"], data["vendor"]
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
    data["flips"] = flips
    data["quality"] = {i: quality[i] for i in shown_ids}


def export(args, db):
    """Write fresh data.json + quests.json 4 th site, renamed into place so th page never fetches half of one."""
    data = market_data(args, db)
    name_shown(args, db, data)
    out = Path(args.out)
    write_json(out, data)
    q = quest_data(args, db)
    write_json(out.with_name("quests.json"), q)
    print(f"exported {data['dumps']} dumps over {data['hours']}h nd {len(q['quests'])} quests 2 {out.parent}")
