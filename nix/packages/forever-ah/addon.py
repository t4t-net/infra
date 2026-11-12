"""ForeverScan's SavedVariables: a tiny lua parser nd th import into th addon_* tables."""
import json
import re
import time
from pathlib import Path


from scrape import aggregate


LUA_TOKEN = re.compile(r'\s+|--[^\n]*|"((?:[^"\\]|\\.)*)"|(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|([\[\]{}=,])|(\w+)', re.S)


LUA_ESCAPE = re.compile(r"\\(\d{1,3}|.)", re.S)


def parse_savedvars(text):
    """Th lua subset wow writes 4 SavedVariables: `Name = value` lines, tables of `["k"] = v,` nd `v, -- [n]`.
    tables w only 1..n keys come back as lists"""
    toks = []
    for m in LUA_TOKEN.finditer(text):
        s, num, punct, word = m.groups()
        if s is not None:
            toks.append(("s", LUA_ESCAPE.sub(lambda e: chr(int(e[1])) if e[1].isdigit() else
                                             {"n": "\n", "t": "\t"}.get(e[1], e[1]), s)))
        elif num is not None:
            toks.append(("v", float(num) if "." in num or "e" in num.lower() else int(num)))
        elif punct:
            toks.append(("p", punct))
        elif word:
            toks.append(("v", {"true": True, "false": False, "nil": None}[word]) if word in ("true", "false", "nil")
                        else ("w", word))
    pos = 0

    def value():
        nonlocal pos
        kind, v = toks[pos]
        pos += 1
        if kind != "p":
            return v
        assert v == "{", f"unexpected {v!r} at token {pos}"
        out, n = {}, 0
        while toks[pos] != ("p", "}"):
            if toks[pos] == ("p", "["):
                pos += 1
                k = value()
                assert toks[pos] == ("p", "]") and toks[pos + 1] == ("p", "="), f"bad key at token {pos}"
                pos += 2
                out[k] = value()
            else:
                n += 1
                out[n] = value()
            if toks[pos] == ("p", ","):
                pos += 1
        pos += 1
        return [out[i] for i in range(1, len(out) + 1)] if out and set(out) == set(range(1, len(out) + 1)) else out

    names = {}
    while pos < len(toks):
        (_, name), eq = toks[pos], toks[pos + 1]
        assert eq == ("p", "="), f"expected = after {name}"
        pos += 2
        names[name] = value()
    return names


TIME_LEFT = {0: "SHORT", 1: "MEDIUM", 2: "LONG", 3: "VERY_LONG"}  # Enum.AuctionHouseTimeLeftBand


def addon_import(args, db):
    """Load ForeverScan's in-game dumps. re-importing th same file is a no-op, scans r keyed by time + character"""
    sv = parse_savedvars(Path(args.savedvars).read_text(encoding="utf-8", errors="replace")).get("ForeverScanDB") or {}
    # ReplicateItems doesnt say wat stacks, so trust whichever endpoint th api listed each item under
    commodities = {i for (i,) in db.execute("select distinct item_id from price where commodity = 1")}
    watched = {i for (i,) in db.execute("select item_id from reagent union select crafted_item_id from recipe")}
    for s in sv.get("scans") or []:
        events = s.get("events") or []
        cur = db.execute(
            "insert or ignore into addon_scan (server_ts, character, house_id, build, listings, missing_info, "
            "first_event_ms, read_ms, forced, timed_out, since_last, sample_links, error) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (s["server_time"], s.get("character") or "?", args.house, s.get("build"), s.get("n"), s.get("missing"),
             events[0]["ms"] if events else None, s.get("read_ms"), int(bool(s.get("forced"))),
             int(bool(s.get("timed_out"))), s.get("since_last"), json.dumps(s["links"]) if s.get("links") else None,
             s.get("error")),
        )
        when = time.strftime("%m-%d %H:%M", time.localtime(s["server_time"]))
        if not cur.rowcount:
            print(f"{when} already imported")
            continue
        sid = cur.lastrowid
        lots = {False: [], True: []}
        listings = []
        # 1: colon separated, 2: tabs + owner (always empty) + suffix, 3: tabs + suffix + bonus ids
        fmt = s.get("format", 1)
        sep = "\t" if fmt >= 2 else ":"
        for row in s.get("rows") or []:
            fields = row.split(sep)
            item, count, buyout, _min_bid, _bid, left = map(int, fields[:6])
            extra = fields[7:] if fmt == 2 else fields[6:]
            suffix = int(extra[0]) if extra and extra[0] not in ("", "0") else None
            bonus = extra[1] if len(extra) > 1 and extra[1] else None
            count = max(count, 1)
            commodity = item in commodities
            # buyout is th whole stack's, same as th api's non-commodity buyout
            unit = buyout // count if buyout else None
            lots[commodity].append({"item": {"id": item}, "quantity": count, "buyout": buyout or None, "unit_price": unit})
            if item in watched or suffix or bonus:
                listings.append((sid, item, unit, count, TIME_LEFT.get(left, str(left)), suffix, bonus))
        db.executemany("insert into addon_price values (?, ?, ?, ?, ?, ?, ?)",
                       [(sid, *r) for c in (False, True) for r in aggregate(lots[c], c)])
        db.executemany("insert into addon_listing values (?, ?, ?, ?, ?, ?, ?)", listings)
        db.commit()
        if s.get("timed_out"):
            print(f"{when} timed out, {s.get('since_last')}s after th previous request")
        elif s.get("error"):
            print(f"{when} partial, {len(listings)} watched/bonus rows b4 th read died at {s['error']}")
            check_against_api(db, sid, args.house, s["server_time"])
        else:
            print(f"{when} {s.get('n')} listings, first update {events[0]['ms'] if events else '?'} ms, "
                  f"{len(listings)} watched/suffixed rows")
            for link in (s.get("links") or [])[:3]:
                print(f"  sample link {link}")
            check_against_api(db, sid, args.house, s["server_time"])

    new = rows = 0
    for p in sv.get("watch_polls") or []:
        cur = db.execute(
            "insert or ignore into addon_watch_poll (server_ts, character, house_id, item_id, results, full, ms) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (p["t"], p.get("c") or "?", args.house, p["item"], p.get("n") or 0, int(bool(p.get("full"))),
             p.get("ms")))
        if not cur.rowcount:
            continue
        new += 1
        book = [r.split(":") for r in (p.get("rows") or "").split(" ") if r]
        db.executemany("insert into addon_watch values (?, ?, ?, ?, ?, ?, ?)",
                       [(cur.lastrowid, rank, int(a), int(price), int(q), int(left), int(owners))
                        for rank, (price, q, a, left, owners) in enumerate(book)])
        rows += len(book)
    db.commit()
    if new:
        print(f"watch: {new} new polls, {rows} listings")

    db.executemany("insert or replace into addon_deposit_duration values (?, ?)",
                   list(enumerate(sv.get("deposit_durations") or [], 1)))
    deposits = [(item, int(d), int(q), int(cost), int(rec.get("kind") == "commodity"), rec["t"])
                for item, rec in (sv.get("deposits") or {}).items()
                for d, q, cost in (c.split(":") for c in rec.get("costs", "").split(" ") if c)]
    # only overwrite w a newer reading, so importing an old file cant roll deposits back
    db.executemany(
        "insert into addon_deposit values (?, ?, ?, ?, ?, ?) on conflict(item_id, duration, quantity) do update "
        "set deposit = excluded.deposit, commodity = excluded.commodity, server_ts = excluded.server_ts "
        "where excluded.server_ts > addon_deposit.server_ts", deposits)
    db.commit()
    if deposits:
        print(f"deposits: {len({d[0] for d in deposits})} items")


def check_against_api(db, sid, house, ts):
    """Median addon/api ratio of median unit prices vs th nearest api dump. ~1 means th per-stack buyout
    assumption holds; a commodity ratio near th avg stack size means th addon's buyouts were per unit after all"""
    near = db.execute("select id from snapshot where house_id = ? order by abs(coalesce(data_ts, ts) - ?) limit 1",
                      (house, ts)).fetchone()
    if not near:
        return
    for commodity in (0, 1):
        ratios = sorted(a / b for a, b in db.execute(
            "select a.median_unit, p.median_unit from addon_price a join price p on p.item_id = a.item_id "
            "and p.commodity = a.commodity where a.scan_id = ? and p.snapshot_id = ? and a.commodity = ? "
            "and p.median_unit > 0", (sid, near[0], commodity)))
        if ratios:
            print(f"  {'commodity' if commodity else 'item'} median price vs api: x{ratios[len(ratios) // 2]:.2f} "
                  f"over {len(ratios)} items")
