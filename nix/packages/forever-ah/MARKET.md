# forever-ah market model

design doc 4 rebuilding th market model (`market_data` in forever_ah.py) instead of patching it again.
status: **draft**, 2026-11-11. open questions r at th bottom nd marked w luna's leanings.

## why rebuild

`market_data` is ~300 lines doing six jobs in one function: inferring sales, liquidity/queue math, relist-war
flags, craft costing, flips + vendor spreads, nd backfilling item names off th api. every heuristic in it
landed as a fix on top of th last one, nd all of them in th last 2 days:

- sales = vanished id → then "not if a cheaper one survived" (bf3d3ad), cuz fresh undercuts ate real sales
- sell timing = units/h → then buying sprees (087ea5d), cuz heavy dynamite said 5m when it was 3h
- liquidity = 1s floor queue (61e522b) → generalizing past th 1s floor is still an open idea
- craft revenue capped at `sold_at` (361a206) cuz resellers relist at 4x b4 dumps
- relist wars (bf3d3ad), then "dried up"
- vendor prices → then server hotfixes (598397a, 0381a84)

none of it has tests. every change got checked by eyeballing th live site. nd now th ForeverScan addon adds
two more data sources tht see th market at totally different resolutions, which th current shape can only
take as more special cases.

## wat th model is 4

th site answers four questions. everything in th model shud exist 2 answer one of them:

1. **wat is this worth 2 me if i list it now?** not th floor, th price stuff actually clears at
2. **how long till it sells, nd wat does waiting cost?** queue ahead, sprees, expired deposits
3. **wat do th inputs cost?** 2 buy th quantity i need, not th median of th whole book
4. **where's free money?** vendor flips, cross-house spreads, crafts w margin

## data sources

| source | cadence | sees | blind 2 |
|---|---|---|---|
| battle.net api | hourly (blizz publishes ~:13, we pull :20), lags up 2 ~1h | every listing w auction id, time-left band, every item, every house | anything inside th hour |
| addon full dump (`ReplicateItems`) | 1 per 15 min, only while ellie is at th AH | every listing, bonus ids (random suffixes), exact book right now | auction ids, owners. only house 111 |
| addon watch (commodity search) | ~every 60-90s per watched item, only while at th AH nd browsing | whole order book as **price levels**: qty, seller count, exact seconds left | individual auctions (levels r merged), non-commodities, anything not watched |
| DBCache.bin | whenever ellie logs in nd we recopy | hotfixed vendor prices | nothing about th AH |

two consequences tht shape everything below:

- **coverage is lumpy.** addon data only exists while ellie plays. a gap in addon data means *we werent
  looking*, never "nothing happened".
- **each source detects sales differently**, so sales inference has 2 b per source nd merged after, not
  one rule bolted onto th api's auction table.

## core shape: observations → fills → market

```
sources ──► observations ──► fills ──► per-item market ──► consumers (crafts, gather, flips, vendor, alert)
              (books)        (sales)    (pure functions)
```

### observations

one normalized type 4 "wat th book looked like at time t":

```
Observation(item, t, source, levels: [(unit_price, qty, owners?, auction_ids?)], complete: bool)
```

api snapshots nd addon dumps produce one per item per dump (levels built by summing listings per price,
keeping ids where we have them). watch polls already r one. `complete` is false when th source only saw
part of th book (a watch poll past th depth cap).

### fills (inferred sales)

each source gets its own inference, all emitting th same thing:

```
Fill(item, t_from, t_to, unit_price, qty, source, confidence)
```

- **api**: wat we do now, kept bc it works: id gone w time left nd not SHORT, nd no cheaper listing from
  th same dump survived → fill. otherwise → pull. `t_from..t_to` is th dump pair, so up 2 an hour wide.
- **watch**: per price level between consecutive polls, using three facts about how commodities trade:
  buyers always take th cheapest units first, a buy can take *part* of a listing, nd a cancel always pulls
  a *whole* listing. so walk th earlier poll's levels from th cheapest up:
  1. **th sweep.** levels tht vanished, then th first level tht shrank but survived, r wat buyers ate.
     those drops r fills. th sweep stops at th first level tht didnt shrink. new levels tht werent in th
     earlier poll (fresh undercuts) r ignored here, they cant have been bought from b4 they existed
  2. **expiry.** a swept level tht vanished w `time_left_s` under th poll gap probably expired. not a fill,
     same idea as th api's SHORT rule but w exact seconds
  3. **above th sweep**, any drop is a cancel, since a buyer wud have taken th cheaper units first. seller
     count going down confirms it (a whole listing left)
  4. **seller counts inside th sweep** sort out th ambiguous cases:
     - qty down, sellers same → partial buy, a fill. cancels cant do tht, they remove whole listings
     - qty down, sellers down → fill if its th bottom of th sweep, but a seller cancelling their only
       listing at th floor looks th same. fill w lower confidence
     - qty down, sellers *up* → someone listed into th level while buyers ate it, so th real fill is
       bigger than th drop. fill of th drop, flagged as a lower bound
  real example (copper bar, 2026-11-11): th 60c level went 33 → 8 w 1 seller → 25 bought fr. next poll
  it was gone (8 units, 2h left, so not expiry) while new 72c nd 75c levels appeared, which reads like a
  buyer finishing it off, or th seller cancelling 2 relist higher. tht one stays a low-confidence fill.
- **addon dump**: no ids, so no fills. its observations still count as th freshest book.

merging: per item, a window covered by watch polls uses watch fills (minute resolution), nd th api's fills
4 tht same window get dropped so nothing is counted twice. outside watch coverage, api fills as now.

### per-item market

pure functions over (observations, fills, params). each quantity defined exactly once:

- **book now**: th freshest observation from any source. floor, nd a depth curve `units_at_or_below(p)`
- **sprees**: fills clustered by time gap. gives spree rate λ (per hour) nd units-per-spree. this is th
  current model's best idea nd it carries over unchanged, just fed sharper fills where watch has them
- **clearing price**: fill-weighted median price over th window. replaces th `min(floor, sold_at)` cap
- **trend**: plain least squares slope of fill prices over th window, weighted by qty, shown on th site
  as copper/h. this is wat th launch-week crash needs: thorium went 3g → 25s in 48h, nd a "price" tht
  ignores tht tells u 2 craft into a falling knife. nothing fancier (decay curves etc) until a straight
  line visibly fails on real data
- **realizable price** 4 a stack of k listed now: undercut th floor by one step (1c commodities, 1s gear),
  but never above clearing price, nd projected along th trend 2 th expected sale time
- **queue + time 2 sell**: units ahead at ur price (from th depth curve, not just th 1s floor case) plus
  ur stack, over units-per-spree → sprees needed → poisson on λ. same math as now, generalized past th
  pinned-floor special case
- **deposit risk**: expected expired listings × deposit, same geometric model as now. deposit per item
  from `CalculateCommodityDeposit` / `CalculateItemDeposit` once th addon records them, flat 1s till then
- **health**: relist war (pulls ≫ fills) nd dried up (expected fills didnt show), same flags as now but
  computed from fills, so watch data makes them sharper too

### consumers

- **crafts**: mat cost = cost 2 *buy th quantity u need* by walking th book cheapest first, not th
  median. on th 2026-11-11 copper bar book (median 85c), ironforge breastplate's 16 bars cost 60c each 4
  one craft, 70c each 4 5, 77c each 4 60, so th median overstated a single craft by 42%. revenue =
  realizable price × avg yield × 0.95. farm rows stay as they r
- **gather, flips, vendor**: unchanged in wat they show, but read th market functions instead of poking
  at `book()` tuples
- **name/quality backfill**: moves out of th model entirely, into export. a model shudnt make api calls

## module layout

```
forever_ah.py   cli + wiring only
scrape.py       api scrape (unchanged)
addon.py        savedvars parser + addon-import
observe.py      sources → observations
fills.py        per-source sale inference + merge
market.py       per-item derived quantities, pure functions
crafts.py       craft/farm costing
export.py       data.json, name backfill, flips, vendor
tact.py, questie.py  unchanged
```

params (`hours`, `deposit`, `war_ratio`, ...) go in as an explicit config object, no globals. th db is
only touched in observe.py nd export.py, so everything in between is testable w plain data.

## testing

- **fixtures from real data**, frozen out of th db as small json: heavy dynamite (sprees), thorium bar
  (launch crash), bronze bar watch polls from 2026-11-11 (th ~370 unit sweep in 2 min), a relist-war item,
  a gear item pinned at 1s
- **golden tests** on th per-item market output 4 each fixture, so a heuristic change shows up as a
  number diff in review, not as "th site looks weird"
- **invariants**: fills never exceed wat vanished, merged fills never double count a window, realizable
  price never above clearing price
- **refactor safety net**: b4 any behavior change, snapshot today's data.json from a frozen db copy nd
  make th split reproduce it byte 4 byte

## migration

1. split th file into th modules above w zero behavior change, proven by th data.json snapshot test
2. build observations + api fills alongside th old code, assert they reproduce today's `sold`/`pulled`
3. add watch fills nd merging, compare against api fills 4 windows both cover
4. swap consumers over 2 th new market functions one at a time (crafts last, its th biggest)
5. delete th old `market_data`

each step is its own commit nd leaves th site working.

## decided

- **watch sales vs cancels**: split w seller counts + th cheapest-first sweep (see fills above). ellie,
  2026-11-11
- **trend**: plain least squares. ellie, 2026-11-11: same family as wat she uses 4 advertising at work,
  so its familiar, nd launch-decay models r more machinery than we need yet
- **crafting quantity (k)**: show both, mat cost 4 one craft nd 4 a batch, where a batch is enough crafts
  2 fill one AH stack of th output: `ceil(output stack size / avg yield)`. ellie, 2026-11-11: batches make
  sense 4 commodities, but gear (stack size 1) isnt crafted in batches, nd there th batch comes out as 1
  craft so th site shows a single number. stack size comes from ItemSparse's `Stackable` (tact already
  reads ItemSparse 4 hotfixes) or th item api, whichever has it 4 forever
- **"book now" nd freshness markers**: th freshest observation wins, whichever source it came from (so
  addon data only ever wins 4 house 111). every number th site shows carries wat it was computed from,
  nd th site marks it real-time (watch poll or addon dump from th last few minutes) vs delayed (th
  hourly api, up 2 ~1h old by th time we pull it). ellie, 2026-11-11. this means th market functions
  return an `as_of` + `source` alongside each value, not bare numbers
- **deposits**: ellie, 2026-11-11, said add real ones 2 th addon. they turned out 2 b an exact formula,
  matching all 228 readings th addon took (37 commodities, 9 gear items, every duration, 1 nd 20 units):

  ```
  deposit = max(100c, vendor sell price × quantity × rate)    rate: 5% 2h, 20% 8h, 60% 24h
  ```

  forever's durations r **2h / 8h / 24h**, not classic's 12/24/48. so th model computes deposits 4 every
  item from item_live's (hotfixed) sell price, nd `addon_deposit` stays as th check tht th formula still
  holds after patches. this kills th flat `--deposit 100` guess, which was badly wrong 4 valuable mats: a
  24h stack of 20 thorium bars is 72s, not 1s. th 1s floor is why every listing ellie made so far cost 1s
- **listing duration is a choice th model makes**, not a constant (`--auction-hours 24` was th longest
  option, not th middle). 2h listings cost 1/12 of 24h ones but need sprees 2 land inside 2h, so per
  item th model picks th duration w th lowest expected deposits lost (sell odds per duration from th
  same poisson spree math) nd shows it

## deferred

- **neutral house cut.** flips assume classic's 15% at blackwater, never verified in forever. ellie
  cant get 2 blackwater yet, so it stays a constant w a comment saying its unverified, nd flips keep
  their "unverified" note on th site
