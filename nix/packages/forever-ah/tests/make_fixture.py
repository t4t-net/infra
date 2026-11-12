#!/usr/bin/env python3
"""Cut a small, committable fixture db out of a real forever-ah.sqlite 4 th snapshot test.

  python3 tests/make_fixture.py SRC.sqlite tests/fixture.sqlite.gz [--hours 12]

keeps th last --hours of dumps 4 house 111 nd blackwater, but only th mining / blacksmithing /
engineering economy (their recipes' mats nd outputs, plus th gathering lists), nd only every --sample'th
auction id of their raw listings. a real db has ~2.5M of those per day, way 2 many 2 commit. sampling by
id (not per dump) keeps th same listings in or out across every dump, so "vanished = sold" still holds
"""
import argparse
import gzip
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game  # noqa: E402
import schema  # noqa: E402

HOUSES = (111, 117)
PROFESSIONS = (186, 164, 202)  # mining, blacksmithing, engineering (heavy dynamite's sprees live here)
QUESTS = 300


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--sample", type=int, default=8, help="keep raw listings whose auction id is divisible by this")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "fixture.sqlite"
        db = sqlite3.connect(dst, uri=True)  # so th source can attach read-only
        db.executescript(schema.SCHEMA)
        db.execute("attach ? as src", (f"file:{args.src}?mode=ro",))
        # th migrations main() runs add these 2 old dbs; th fixture gets them up front
        for col in ("spell_id", "learn_skill", "yellow_skill", "grey_skill"):
            if col not in {c[1] for c in db.execute("pragma table_info(recipe)")}:
                db.execute(f"alter table recipe add column {col} integer")

        last = db.execute("select max(ts) from src.snapshot where house_id = 111").fetchone()[0]
        # a dump before th window too, so th first pair in th window has something 2 diff against
        since = last - args.hours * 3600 - 3600
        db.execute(f"insert into snapshot select * from src.snapshot where house_id in {HOUSES} and ts >= ?", (since,))

        recipes = [r for (r,) in db.execute(
            f"select id from src.recipe where profession_id in {PROFESSIONS}")]
        marks = ",".join("?" * len(recipes))
        items = {i for (i,) in db.execute(
            f"select item_id from src.reagent where recipe_id in ({marks}) union "
            f"select crafted_item_id from src.recipe where id in ({marks}) and crafted_item_id is not null",
            recipes + recipes)}
        items |= {i for ids in game.GATHERED.values() for i in ids}
        db.execute("create temp table keep (id integer primary key)")
        db.executemany("insert or ignore into keep values (?)", [(i,) for i in items])

        db.execute(f"insert into recipe select * from src.recipe where profession_id in {PROFESSIONS}")
        db.execute(f"insert into reagent select * from src.reagent where recipe_id in ({marks})", recipes)
        db.execute("insert into price select p.* from src.price p join snapshot s on s.id = p.snapshot_id "
                   "where p.item_id in (select id from keep)")
        db.execute("insert into auction select a.* from src.auction a join snapshot s on s.id = a.snapshot_id "
                   "where a.item_id in (select id from keep) and a.auction_id % ? = 0", (args.sample,))

        # quests: th first few hundred alliance ones, nd every item their rewards name
        db.execute("insert into quest select * from src.quest where (faction is null or faction = 'ALLIANCE') "
                   "and name not like '<%' and zone_name is not null order by id limit ?", (QUESTS,))
        for choice, fixed in db.execute("select reward_choice, reward_fixed from quest").fetchall():
            for ids in (choice, fixed):
                db.executemany("insert or ignore into keep values (?)",
                               [(i,) for i in json.loads(ids or "[]")])
        for table in ("item", "item_hotfix", "item_quality"):
            db.execute(f"insert into {table} select * from src.{table} where id in (select id from keep)")
        # export backfills names nd qualities 4 anything it shows off th api, nd th test runs offline. th real
        # db only cached wat th live site happened 2 show, so fill th rest w stand-ins
        db.execute("insert into item_quality select id, 'common' from keep where id not in (select id from item_quality)")
        db.execute("insert into item (id, name, found) select k.id, coalesce(h.name, 'item ' || k.id), 1 from keep k "
                   "left join item_hotfix h on h.id = k.id where k.id not in (select id from item)")
        db.execute("update item set name = coalesce((select h.name from item_hotfix h where h.id = item.id), "
                   "'item ' || id) where name is null")
        db.commit()
        db.execute("detach src")
        db.execute("vacuum")
        db.close()

        with open(dst, "rb") as f, gzip.open(args.out, "wb", compresslevel=9) as g:
            shutil.copyfileobj(f, g)
    print(f"{args.out}: {Path(args.out).stat().st_size // 1024}k, last dump {last}")


if __name__ == "__main__":
    main()
