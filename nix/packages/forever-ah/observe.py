"""sources → observations: wat th book looked like 4 one item at one time, whichever source saw it.

th only module in th model tht reads th db. everything downstream (fills, market) is plain data in, plain
data out, so its testable w hand-built observations. see MARKET.md
"""
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    unit_price: int | None          # None 4 bid-only
    quantity: int
    auction_id: int | None = None   # api: th auction. watch: th price level's representative
    time_left: str | None = None    # api band: SHORT, MEDIUM, LONG, VERY_LONG
    time_left_s: int | None = None  # watch: exact seconds (jumps up when a fresh listing joins th level)
    owners: int | None = None       # watch: sellers summed into this price level


@dataclass(frozen=True)
class Observation:
    item_id: int
    t: int                          # when th book looked like this (blizz's dump time 4 th api)
    source: str
    listings: tuple[Listing, ...]   # empty when th item had nothing up
    complete: bool = True           # false when th source only saw th cheap end (a watch poll past its cap)


def api_dumps(db, house, since):
    """(snapshot id, dump time) 4 each distinct api dump of house since `since`, oldest first. scrapes from
    before Last-Modified tracking can repeat a dump, so dumps r deduped on their time"""
    dumps, seen = [], set()
    for sid, ts, dts in db.execute(
            "select id, ts, data_ts from snapshot where house_id = ? and ts >= ? order by ts", (house, since)):
        if (dts or ts) not in seen:
            seen.add(dts or ts)
            dumps.append((sid, dts or ts))
    return dumps


def api_observations(db, dumps):
    """{item: [Observation per dump]} from th raw listings (watched items only). every item gets one per dump,
    empty where it had nothing up, so 'all its listings vanished' is a pair like any other"""
    by_dump = defaultdict(lambda: defaultdict(list))
    marks = ",".join("?" * len(dumps))
    for sid, aid, iid, price, q, tl in db.execute(
            f"select snapshot_id, auction_id, item_id, unit_price, quantity, time_left from auction "
            f"where snapshot_id in ({marks})", [sid for sid, _ in dumps]):
        by_dump[sid][iid].append(Listing(price, q, aid, tl))
    items = {i for listed in by_dump.values() for i in listed}
    return {i: [Observation(i, t, "api", tuple(by_dump[sid].get(i, ()))) for sid, t in dumps] for i in items}


def newest_addon_dump(db, house, after, until):
    """(scan id, time) of th addon's newest whole full dump in (after, until], or None. timed out nd died-midway
    reads r skipped: a partial dump is missing items at random, so it cant stand in 4 th whole book"""
    return db.execute(
        "select id, server_ts from addon_scan where house_id = ? and server_ts > ? and server_ts <= ? "
        "and listings is not null and not timed_out and error is null order by server_ts desc limit 1",
        (house, after, until)).fetchone()


def addon_books(db, scan_id):
    """{item: (median, min, quantity, auctions)} from a full addon dump, shaped like th api's price rows"""
    return {i: (med, mn, q, n) for i, med, mn, q, n in db.execute(
        "select item_id, median_unit, min_unit, quantity, auctions from addon_price where scan_id = ? "
        "order by quantity", (scan_id,))}


def addon_observations(db, scan_id, t):
    """{item: Observation} from a full addon dump's raw rows (watched items nd suffixed gear only). no auction
    ids, so these r books 2 price against, not something fills can follow across dumps"""
    rows = defaultdict(list)
    for iid, price, q, tl in db.execute(
            "select item_id, unit_price, quantity, time_left from addon_listing where scan_id = ?", (scan_id,)):
        rows[iid].append(Listing(price, q, time_left=tl))
    return {i: Observation(i, t, "addon", tuple(ls)) for i, ls in rows.items()}


def watch_observations(db, house):
    """{item: [Observation per poll]} from th addon's watchlist. each listing is a whole price level (every
    seller at tht unit price summed), cheapest first"""
    polls = defaultdict(list)
    levels = defaultdict(list)
    for pid, price, q, aid, left, owners in db.execute(
            "select w.poll_id, w.unit_price, w.quantity, w.auction_id, w.time_left_s, w.owners from addon_watch w "
            "join addon_watch_poll p on p.id = w.poll_id where p.house_id = ? order by w.poll_id, w.rank", (house,)):
        levels[pid].append(Listing(price, q, aid, time_left_s=left, owners=owners))
    for pid, iid, t, results, full in db.execute(
            "select id, item_id, server_ts, results, full from addon_watch_poll where house_id = ? "
            "order by item_id, server_ts", (house,)):
        got = tuple(levels.get(pid, ()))
        polls[iid].append(Observation(iid, t, "watch", got, complete=bool(full) and results <= len(got)))
    return dict(polls)
