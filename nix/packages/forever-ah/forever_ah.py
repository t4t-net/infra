#!/usr/bin/env python3
"""WoW: Forever auction house tracker.

  forever-ah scrape   snapshot every house as per-item aggregates, plus raw auctions 4 watched items
  forever-ah recipes  cache profession recipes + item vendor prices from th static api
  forever-ah quests   cache quests: questie's levels/givers/chains + th api's rewards
  forever-ah analyze  craft profitability 4 one house from th latest snapshot
  forever-ah export   write a fresh data.json 4 th gold meta site
  forever-ah alert    post newly opened flips 2 discord
  forever-ah addon-import  load in-game full AH dumps from th ForeverScan addon's SavedVariables

creds: BNET_CLIENT_ID / BNET_CLIENT_SECRET, or ~/.secrets/battle-net-client-{id,secret}
"""
import argparse
import os

from addon import addon_import
from crawl import hotfixes, quests, recipes
from export import alert, export
from game import PROFESSIONS
from market import analyze
import schema
from scrape import scrape


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
    hp = sub.add_parser("hotfixes")
    hp.add_argument("dbcache", help="Cache/ADB/enUS/DBCache.bin from a forever client")
    hp.add_argument("--product", default="wowf", help="client product on blizzard's version service (wowf is forever)")
    hp.add_argument("--cache", default=os.environ.get("FOREVER_AH_CDN_CACHE", "cdn-cache"),
                    help="CDN cache; content-addressed, so it only grows across patches")
    ip = sub.add_parser("addon-import")
    ip.add_argument("savedvars", help="WTF/Account/*/SavedVariables/ForeverScan.lua")
    ip.add_argument("--house", type=int, default=111, help="house th dumps came from, th addon cant tell")
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
    ex.add_argument("--now", type=int, help="unix time 2 export as of, 4 tests (default: th real now)")
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

    db = schema.connect(args.db)
    {"scrape": scrape, "recipes": recipes, "quests": quests, "hotfixes": hotfixes, "addon-import": addon_import, "analyze": analyze, "export": export, "alert": alert}[args.cmd](args, db)


if __name__ == "__main__":
    main()
