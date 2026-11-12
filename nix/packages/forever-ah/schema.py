"""th sqlite schema nd th migrations old dbs need, in one place."""
import sqlite3

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
-- ItemSparse rows blizz patched server side (iron grenade vendors 4 125c, not th api's 500c), from a
-- client's DBCache.bin. its own table cuz scrape's backfill rewrites item from th api
create table if not exists item_hotfix (
  id integer primary key,
  name text not null,             -- also names forever-only items th api 404s on
  sell_price integer,             -- null 4 items th server sent on lookup, their prices r junk
  purchase_price integer,
  push_id integer not null
);
create view if not exists item_live as
  select i.id, coalesce(i.name, h.name) as name, coalesce(h.sell_price, i.sell_price) as sell_price,
         coalesce(h.purchase_price, i.purchase_price) as purchase_price
  from item i left join item_hotfix h on h.id = i.id;
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

-- in-game full dumps from th ForeverScan addon (C_AuctionHouse.ReplicateItems). kept apart from snapshot
-- cuz they carry no auction ids, so th vanished-id sales logic wud read every addon dump as a sellout.
-- timed out requests r kept 2, they're th record of how often th server lets us dump
create table if not exists addon_scan (
  id integer primary key,
  server_ts integer not null,     -- GetServerTime() when ReplicateItems went out
  character text not null,
  house_id integer not null,      -- th addon cant tell, so its whatever import was told
  build text,
  listings integer,               -- null when th request timed out
  missing_info integer,           -- rows w/o full item info at read time
  first_event_ms integer,         -- request -> first REPLICATE_ITEM_LIST_UPDATE
  read_ms integer,                -- request -> rows read
  forced integer not null,        -- updates never went quiet, rows read at th settle cap
  timed_out integer not null,
  since_last integer,             -- seconds since th previous request, 4 working out th throttle
  sample_links text,              -- json, a few raw item strings 2 check th suffix field position against
  error text,                     -- th addon's read died here; rows up 2 it r still imported
  unique (server_ts, character)
);
create table if not exists addon_price (
  scan_id integer not null references addon_scan(id),
  item_id integer not null,
  commodity integer not null,     -- guessed from th api's commodity flag, 0 4 items it never listed
  min_unit integer not null,
  median_unit integer not null,
  quantity integer not null,
  auctions integer not null,
  primary key (scan_id, item_id, commodity)
);
-- raw listings 4 watched items nd random-suffix gear, like auction but w no id 2 follow across dumps.
-- forever's ReplicateItems leaves owners empty, so there's no seller 2 key on either
create table if not exists addon_listing (
  scan_id integer not null references addon_scan(id),
  item_id integer not null,
  unit_price integer,             -- null 4 bid-only
  quantity integer not null,
  time_left text not null,
  suffix integer,                 -- item string's classic suffix field, null when empty (so far always)
  bonus text                      -- comma separated bonus ids, where forever actually puts "of th monkey"
);
create index if not exists addon_listing_item on addon_listing(item_id);
-- th addon's watchlist: a commodity search every ~minute per item. rows r PRICE LEVELS, not auctions:
-- every seller at one unit price is summed in2 one row (owners counts them), nd its auction_id is a
-- representative tht stays put while th level lives. so sales show up as a level's quantity dropping
-- (net of new listings joining it) or a level below th new floor vanishing, timed 2 th minute
create table if not exists addon_watch_poll (
  id integer primary key,
  server_ts integer not null,
  character text not null,
  house_id integer not null,
  item_id integer not null,
  results integer not null,       -- price levels th search reported, before th depth cap
  full integer not null,          -- th client had every result, not just th first page
  ms integer,                     -- search -> results
  unique (server_ts, character, item_id)
);
create table if not exists addon_watch (
  poll_id integer not null references addon_watch_poll(id),
  rank integer not null,          -- 0 = cheapest
  auction_id integer not null,
  unit_price integer not null,
  quantity integer not null,
  time_left_s integer,            -- exact seconds, not th api's bands. jumps up when a fresh listing joins
  owners integer,                 -- how many sellers r behind this price level
  primary key (poll_id, rank)
);
create index if not exists addon_watch_auction on addon_watch(auction_id);
-- real deposits from th addon (CalculateCommodityDeposit / CalculateItemDeposit), latest reading wins.
-- gear only gets priced while its in ellie's bags, so coverage grows as she plays
create table if not exists addon_deposit (
  item_id integer not null,
  duration integer not null,      -- blizz's dropdown index, 1-3; labels in addon_deposit_duration
  quantity integer not null,
  deposit integer not null,       -- copper
  commodity integer not null,
  server_ts integer not null,
  primary key (item_id, duration, quantity)
);
create table if not exists addon_deposit_duration (
  duration integer primary key,
  label text not null             -- wat th sell dropdown says, e.g. "12 Hours"
);
"""


def connect(path):
    # scrape nd recipes share th db on a timer, so wait out th other's write lock instead of dying
    db = sqlite3.connect(path, timeout=60)
    db.executescript(SCHEMA)
    if "data_ts" not in {c[1] for c in db.execute("pragma table_info(snapshot)")}:
        db.execute("alter table snapshot add column data_ts integer")
    # item_hotfix's prices started out not null, nd its just a copy of th last DBCache load
    if any(c[1] == "sell_price" and c[3] for c in db.execute("pragma table_info(item_hotfix)")):
        db.execute("drop table item_hotfix")
        db.executescript(SCHEMA)
    have = {c[1] for c in db.execute("pragma table_info(recipe)")}
    for col in ("spell_id", "learn_skill", "yellow_skill", "grey_skill"):
        if col not in have:
            db.execute(f"alter table recipe add column {col} integer")
    return db
