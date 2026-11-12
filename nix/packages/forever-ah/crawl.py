"""th slow crawls: recipes (+ client tables off th cdn), DBCache hotfixes, nd quests."""
import json
import sys
from pathlib import Path

import questie
import tact

from api import Client, creds
from game import ALLIANCE_RACES, HORDE_RACES


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


ITEM_SPARSE = 1572924  # FileDataID


ITEM_SPARSE_HASH = 0x919BE54E  # table hash, wat DBCache.bin keys rows by


def hotfixes(args, db):
    """Load vendor prices from a client's DBCache.bin. th client only refreshes it at login, so recopy it now nd then."""
    build, rows = tact.read_dbcache(Path(args.dbcache).read_bytes())
    st = tact.Storage(args.product, args.cache)
    # hotfix rows r laid out like th live db2's records, so th cdn's copy tells us which layout 2 walk
    fields = tact.inline_fields(st.files([ITEM_SPARSE])[ITEM_SPARSE], tact.http(tact.DBD.format(table="ItemSparse")).decode())
    if not st.cdn.build.endswith(f".{build}"):
        sys.exit(f"DBCache is from build {build} but th cdn serves {st.cdn.build}, log in on th new client nd recopy it")
    fixed = []
    for (table, rid), (push, status, rec) in rows.items():
        if table != ITEM_SPARSE_HASH or status != tact.HOTFIX_VALID:
            continue
        row, end = tact.walk_record(rec, fields)
        if not 0 <= len(rec) - end < 4:
            sys.exit(f"item {rid}: walked {end} of {len(rec)} bytes, dbd layout doesnt match")
        # items th client didnt ship w come back from a server lookup under push 0x1000000 | id instead of a
        # real push. th names r right but th prices arent (moongazer's wand: 373s here, 8s86c in game)
        if push & tact.HOTFIX_LOOKUP:
            fixed.append((rid, row["Display_lang"], None, None, push))
        else:
            fixed.append((rid, row["Display_lang"], row["SellPrice"], row["BuyPrice"], push))
    # th cache is a full picture of wat th server pushed, so replace rather than merge
    db.execute("delete from item_hotfix")
    db.executemany("insert into item_hotfix values (?, ?, ?, ?, ?)", fixed)
    db.commit()
    moved = db.execute("select count(*) from item i join item_hotfix h on h.id = i.id where i.sell_price != h.sell_price").fetchone()[0]
    print(f"build {build}: {len(fixed)} hotfixed items, {moved} vendor prices differ from th api", flush=True)


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
