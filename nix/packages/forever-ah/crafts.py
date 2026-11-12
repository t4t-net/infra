"""craft nd farm-it-urself tables: every recipe priced 2 buy (or farm) nd sell, from th per-item market."""
from collections import defaultdict

from game import GATHERED, PROFESSIONS, VENDOR_MATS


def craft_tables(db, now, items, market, buy_cost):
    """{profession: top/starters/farmed rows nd counts}. now is {item: (median, floor, qty, listings)}, items is
    {item: (name, sell price, buy price)}, market(item, stack) is th per-item market row, nd buy_cost(item, q)
    is wat q of an item costs bought cheapest first"""
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

    def farmed(i, prof, busy=frozenset(), q=1):
        """(copper, {(item, source): qty}) per one of item i when getting q of them, or None if theres no way"""
        nm, _, buy = items.get(i, (None, None, None))
        if nm in VENDOR_MATS and buy:
            return buy, {(i, "vendor"): 1}
        best = None
        for pid, rid, per in makers.get(i, []):
            # leather etc drop as-is, only bars get made (else heavy leather turns into 17k ruined scraps lol)
            if pid not in ((186,) if i in gathered else (prof, 186)) or rid in busy:
                continue
            got = farm_recipe(rid, prof, busy | {rid}, q / per)
            if got and (best is None or got[0] / per < best[0]):
                best = (got[0] / per, {k: q / per for k, q in got[1].items()})
        if best and any(src == "farm" for _, src in best[1]):
            return best
        # GATHERED has bars in it 4 th mining page, so this comes after th smelt check
        if i in gathered:
            return 0, {(i, "farm"): 1}
        if i in now:
            return buy_cost(i, q) / q, {(i, "ah"): 1}
        return best

    def farm_recipe(rid, prof, busy=frozenset(), times=1):
        """(copper, {(item, source): qty}) per craft when crafting it `times` times"""
        cost, need = 0, defaultdict(float)
        for i, q in reagents[rid]:
            got = farmed(i, prof, busy, q * times)
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
                    cost += buy_cost(i, q)
                    mats.append({"id": i, "name": nm or f"item {i}", "qty": q})
                else:
                    ok = False
            if not ok or not cost:
                continue
            per = (cmin + cmax) / 2
            m = market(out, per)
            # th sales rate was earned at wat things actually sold 4, so never price above tht. a reseller who
            # buys out th floor nd relists at 4x right b4 a dump would otherwise turn a loser into a top craft
            rev = int(m["realizable"] * per * 0.95)
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
    return crafts
