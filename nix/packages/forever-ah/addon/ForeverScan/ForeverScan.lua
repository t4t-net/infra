-- ForeverScan: pull th AH into SavedVariables 4 forever-ah while ellie stands at it.
-- full dump: opens th AH -> C_AuctionHouse.ReplicateItems() (1 per 15 min) -> every listing.
-- watch: round-robin commodity searches on a watchlist, ~1/min per item, cheapest listings w auction ids
-- so sales show up minute by minute. rows land in ForeverScanDB on /reload or logout.
-- only read-side api here, nothing tht buys/posts/cancels (those need a hardware event anyway)

local KEEP_SCANS = 3      -- full dumps r a few mb each, dont let th saved file grow forever
local QUIET_S = 3         -- REPLICATE_ITEM_LIST_UPDATE can fire more than once, wait 4 it 2 settle
local MAX_SETTLE_S = 30   -- read anyway this long after th first update
local TIMEOUT_S = 120     -- no event by then = throttled or unsupported, log it
local CHUNK = 1000        -- rows read per frame, small enough 2 stay under "script ran too long"
local SAMPLE_LINKS = 20
local DUMP_EVERY_S = 900
local WATCH_EVERY_S = 5   -- 1 search per tick, blizz allows 100/min nd ellie's own clicking needs some
local WATCH_DEPTH = 100   -- cheapest listings kept per poll, th rest of th book barely moves
local WATCH_KEEP = 5000   -- polls kept in th saved file, ~7h of a 12 item list
local WATCH_WAIT_S = 30   -- give up on a search tht never answered
local REMIND_S = 900      -- data only in memory this long gets a "reload 2 save it?" popup
-- busiest commodities in house 111 (most listings gone per dump, 2026-11-11) + ellie's mining/bs bars,
-- then (v2) th ores nd tin bar so smelting spreads come from th same minute
local WATCH_DEFAULT = { 12359, 3860, 3575, 2841, 2840, 1081, 5784, 774, 814, 4306, 2592, 2589,
                        2770, 2771, 3576, 2772, 3858, 10620 }
local WATCH_DEFAULT_VERSION = 2
local WATCH_DEFAULT_V1 = 12  -- how many of WATCH_DEFAULT a v1 list already got

-- every timestamp comes from th pc's own clock. forever's now() came back from a relog on
-- 2026-11-12 reading pacific wall time as if it were utc (exactly 8h behind time()), which made th dump
-- throttle wait ~6h nd stamped watch polls in th past. th saved keys r still called server_time / t so old
-- files nd th importer keep working
local now = time

local db
local watch = { i = 0 }   -- pending = th search waiting on its results
local ticker
local savedThrough        -- time th saved file covers: everything up 2 this login or /reload
local snoozeUntil = 0
local scan                -- th scan in flight, nil when idle
local gen = 0             -- bumps on every update so stale settle timers bail

local function say(fmt, ...)
    print(("|cffd4af37ForeverScan|r: " .. fmt):format(...))
end

local function elapsed()
    return floor(debugprofilestop() - scan.t0)
end

local function store(done)
    table.insert(db.scans, done)
    while #db.scans > KEEP_SCANS do
        table.remove(db.scans, 1)
    end
end

local function finish()
    local s = scan
    local n = C_AuctionHouse.GetNumReplicateItems()
    s.n, s.rows, s.missing, s.links, s.format = n, {}, 0, {}, 3
    local i = 0
    local step
    -- errors r hidden by default nd a dead step leaves th scan "in flight" forever, so catch, keep wat we
    -- read so far, nd say where it broke
    local function guarded()
        local ok, err = pcall(step)
        if not ok then
            s.error = ("row %d: %s"):format(i, tostring(err))
            s.read_ms = elapsed()
            scan = nil
            store(s)
            say("|cffff4040read failed|r at %s. /reload 2 save wat we got", s.error)
        end
    end
    step = function()
        for _ = 1, CHUNK do
            if i >= n then
                s.read_ms = elapsed()
                scan = nil
                store(s)
                say("%d listings (%d w/o full item info), %d update events, first %s ms, read at %d ms%s. /reload 2 save",
                    n, s.missing, #s.events, s.events[1] and s.events[1].ms or "?", s.read_ms,
                    s.forced and " (never went quiet)" or "")
                return
            end
            -- name, texture, count, quality, usable, level, levelType, minBid, minIncrement, buyout,
            -- bidAmount, highBidder, bidderFullName, owner, ownerFullName, saleStatus, itemID, hasAllInfo
            -- owner/ownerFullName come back empty from forever's ReplicateItems, so they're not kept
            local _, _, count, _, _, _, _, minBid, _, buyout, bid, _, _, _, _, _, itemID, hasAll =
                C_AuctionHouse.GetReplicateItemInfo(i)
            if not hasAll then
                s.missing = s.missing + 1
            end
            -- full links r ~80 chars x 240k rows, so keep just wat tells random greens apart (they share an
            -- item id) nd a few raw links 2 check th field order against. forever puts "of th monkey" in
            -- bonus ids, not th suffix field: item:15933::::::::19:1486:::1:12732:: is 1 bonus, 12732
            local link = C_AuctionHouse.GetReplicateItemLink(i)
            local itemString = link and link:match("|H(item:[^|]+)|h")
            local suffix, bonus = "", ""
            if itemString then
                local parts = { strsplit(":", itemString) }
                suffix = parts[8] or ""
                local nb = tonumber(parts[14]) or 0
                if nb > 0 then
                    bonus = table.concat(parts, ",", 15, 14 + nb)
                end
                -- th first few, plus a few more w bonus ids so there's always some of those 2 eyeball
                if #s.links < SAMPLE_LINKS or (bonus ~= "" and #s.links < SAMPLE_LINKS * 2) then
                    s.links[#s.links + 1] = itemString
                end
            end
            -- money as %.0f: wow's %d is 32 bit nd troll listings sit at 99,999,999g (999999999999990c)
            s.rows[#s.rows + 1] = ("%d\t%d\t%.0f\t%.0f\t%.0f\t%d\t%s\t%s"):format(itemID or 0, count or 0, buyout or 0,
                minBid or 0, bid or 0, C_AuctionHouse.GetReplicateItemTimeLeft(i) or -1, suffix, bonus)
            i = i + 1
        end
        C_Timer.After(0, guarded)
    end
    guarded()
end

local function start(force)
    if scan then
        say("already scanning (%d ms in)", elapsed())
        return
    end
    -- forever allows 1 full dump per 15 min, counted from th last one tht delivered. throttled
    -- requests dont reset it, they just come back empty, so skip rather than burn a timeout
    local wait = db.last_dump and (db.last_dump + DUMP_EVERY_S - now())
    if wait and wait > DUMP_EVERY_S then
        -- th last dump is in th future, so a clock jumped. th real throttle is unknowable, just try
        say("last dump is %dm in th future, clock jumped? trying anyway", floor((wait - DUMP_EVERY_S) / 60))
        wait = nil
    end
    if wait and wait > 0 and not force then
        say("last dump was %ds ago, next one allowed in %dm%02ds (/fscan force 2 try anyway)",
            DUMP_EVERY_S - wait, floor(wait / 60), wait % 60)
        return
    end
    local version, build, _, toc = GetBuildInfo()
    scan = {
        t0 = debugprofilestop(),
        server_time = now(),
        server_clock = GetServerTime(),  -- blizz's idea of th time, kept 2 spot it drifting again
        build = ("%s.%s"):format(version, build),
        toc = toc,
        faction = UnitFactionGroup("player"),
        character = UnitName("player"),
        since_last = db.last_request and (now() - db.last_request) or nil,
        events = {},
        throttle = {},
    }
    db.last_request = scan.server_time
    C_AuctionHouse.ReplicateItems()
    say("ReplicateItems sent")
    local s = scan
    C_Timer.After(TIMEOUT_S, function()
        if scan == s and #s.events == 0 then
            s.timed_out = true
            scan = nil
            store(s)
            say("no data after %ds, probably throttled (%s s since last request)", TIMEOUT_S, tostring(s.since_last))
        end
    end)
end

-- blizz's commodity list nd commodity sell frame reset on ANY COMMODITY_SEARCH_RESULTS_UPDATED, w/o
-- checking th item, so only search while ellie is browsing, never on a commodity buy/sell screen
local function watchSafe()
    if not AuctionHouseFrame or not AuctionHouseFrame:IsShown() then
        return false
    end
    local mode = AuctionHouseFrame:GetDisplayMode()
    return mode == AuctionHouseFrameDisplayMode.Buy or mode == AuctionHouseFrameDisplayMode.ItemBuy
end

-- wow only writes SavedVariables on /reload or logout, nd th gaming pc only ships th file when it changes.
-- so data sitting in memory isnt on forever-gold yet. a reload only from a click: never a surprise one
-- mid-purchase
StaticPopupDialogs.FOREVERSCAN_RELOAD = {
    text = "ForeverScan has %s of AH data only in memory. Reload 2 save it so forever-gold gets it?",
    button1 = "Reload",
    button2 = "Later",
    OnAccept = function()
        ReloadUI()
    end,
    OnCancel = function()
        snoozeUntil = now() + REMIND_S
    end,
    timeout = 0,
    whileDead = true,
    hideOnEscape = true,
    preferredIndex = 3,
}

local function remind(anyAge)
    if InCombatLockdown() or scan or now() < snoozeUntil then
        return
    end
    local oldest
    for k = #db.watch_polls, 1, -1 do
        local p = db.watch_polls[k]
        if p.t <= savedThrough then
            break
        end
        oldest = p.t
    end
    for _, s in ipairs(db.scans) do
        if s.n and s.server_time > savedThrough then
            oldest = math.min(oldest or s.server_time, s.server_time)
        end
    end
    local age = oldest and now() - oldest
    if not age or (not anyAge and age < REMIND_S) then
        return
    end
    snoozeUntil = now() + REMIND_S
    StaticPopup_Show("FOREVERSCAN_RELOAD", age < 120 and "a minute" or ("%d minutes"):format(floor(age / 60)))
end

local function watchTick()
    remind(false)
    local list = db.watchlist
    if not db.watch_on or #list == 0 or scan or not watchSafe() then
        return
    end
    if watch.pending and now() - watch.pending.server_time < WATCH_WAIT_S then
        return
    end
    if not C_AuctionHouse.IsThrottledMessageSystemReady() then
        return
    end
    watch.i = watch.i % #list + 1
    local item = list[watch.i]
    watch.pending = { item = item, t0 = debugprofilestop(), server_time = now() }
    C_AuctionHouse.SendSearchQuery(C_AuctionHouse.MakeItemKey(item),
        { { sortOrder = Enum.AuctionHouseSortOrder.Price, reverseSort = false } }, false)
end

local function watchRead(item)
    local p = watch.pending
    if not p or p.item ~= item then
        return
    end
    watch.pending = nil
    local n = C_AuctionHouse.GetNumCommoditySearchResults(item)
    local rows = {}
    for j = 1, math.min(n, WATCH_DEPTH) do
        local r = C_AuctionHouse.GetCommoditySearchResultInfo(item, j)
        if r then
            -- all %.0f: wow's %d is 32 bit nd one of these comes back as 2^31
            rows[#rows + 1] = ("%.0f:%.0f:%.0f:%.0f:%.0f"):format(r.unitPrice or 0, r.quantity or 0, r.auctionID or 0,
                r.timeLeftSeconds or -1, r.totalNumberOfOwners or 0)
        end
    end
    local polls = db.watch_polls
    polls[#polls + 1] = {
        t = p.server_time, c = UnitName("player"), item = item, ms = floor(debugprofilestop() - p.t0), n = n,
        full = C_AuctionHouse.HasFullCommoditySearchResults(item), rows = table.concat(rows, " "),
    }
    while #polls > WATCH_KEEP do
        table.remove(polls, 1)
    end
end

-- deposits 4 real instead of export's flat 1s guess. commodities only need an item id; gear needs an
-- ItemLocation, so it can only b priced while its in ellie's bags (which is wat she'd list anyway).
-- every duration (blizz's dropdown, labels saved alongside), nd 1 vs a full stack 2 see if it scales
local DEPOSIT_QTYS = { 1, 20 }

local function recordDeposits()
    local t, done = now(), {}
    db.deposit_durations = { AUCTION_DURATION_ONE, AUCTION_DURATION_TWO, AUCTION_DURATION_THREE }
    local function put(id, kind, calc)
        done[id] = true
        local costs = {}
        for duration = 1, 3 do
            for _, q in ipairs(kind == "item" and { 1 } or DEPOSIT_QTYS) do
                -- soulbound nd quest items in bags cant b auctioned, whatever th api does about tht
                local ok, cost = pcall(calc, duration, q)
                if ok and cost then
                    costs[#costs + 1] = ("%d:%d:%.0f"):format(duration, q, cost)
                end
            end
        end
        if #costs > 0 then
            db.deposits[id] = { t = t, kind = kind, costs = table.concat(costs, " ") }
        end
    end
    local function commodity(id)
        return function(duration, q)
            return C_AuctionHouse.CalculateCommodityDeposit(id, duration, q)
        end
    end
    for _, id in ipairs(db.watchlist) do
        put(id, "commodity", commodity(id))
    end
    for bag = 0, NUM_BAG_SLOTS do
        for slot = 1, C_Container.GetContainerNumSlots(bag) do
            local id = C_Container.GetContainerItemID(bag, slot)
            if id and not done[id] then
                local loc = ItemLocation:CreateFromBagAndSlot(bag, slot)
                local ok, status = pcall(C_AuctionHouse.GetItemCommodityStatus, loc)
                if ok and status == Enum.ItemCommodityStatus.Commodity then
                    put(id, "commodity", commodity(id))
                elseif ok and status == Enum.ItemCommodityStatus.Item then
                    put(id, "item", function(duration)
                        return C_AuctionHouse.CalculateItemDeposit(loc, duration, 1)
                    end)
                end
            end
        end
    end
end

-- C_Item moved around between client flavours, so dont bet on either one
local function itemName(id)
    local name = C_Item and C_Item.GetItemNameByID and C_Item.GetItemNameByID(id)
    return name or (GetItemInfo and GetItemInfo(id)) or tostring(id)
end

local function itemArg(arg)
    return tonumber(arg) or tonumber(arg and arg:match("item:(%d+)"))
end

local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_LOADED")
f:SetScript("OnEvent", function(_, event, arg)
    if event == "ADDON_LOADED" then
        if arg ~= "ForeverScan" then
            return
        end
        ForeverScanDB = ForeverScanDB or {}
        db = ForeverScanDB
        db.scans = db.scans or {}
        -- scans saved b4 last_dump existed still know when they delivered
        if not db.last_dump then
            for _, s in ipairs(db.scans) do
                if s.n and not s.reread and s.server_time > (db.last_dump or 0) then
                    db.last_dump = s.server_time
                end
            end
        end
        if not db.watchlist then
            db.watchlist = CopyTable(WATCH_DEFAULT)
            db.watch_defaults = WATCH_DEFAULT_VERSION
        elseif (db.watch_defaults or 1) < WATCH_DEFAULT_VERSION then
            -- merge defaults added since, but leave anything ellie dropped on purpose dropped
            for k = WATCH_DEFAULT_V1 + 1, #WATCH_DEFAULT do
                if not tContains(db.watchlist, WATCH_DEFAULT[k]) then
                    table.insert(db.watchlist, WATCH_DEFAULT[k])
                end
            end
            db.watch_defaults = WATCH_DEFAULT_VERSION
        end
        if db.watch_on == nil then
            db.watch_on = true
        end
        db.watch_polls = db.watch_polls or {}
        db.deposits = db.deposits or {}
        savedThrough = now()
        f:RegisterEvent("AUCTION_HOUSE_SHOW")
        f:RegisterEvent("AUCTION_HOUSE_CLOSED")
        f:RegisterEvent("REPLICATE_ITEM_LIST_UPDATE")
        f:RegisterEvent("COMMODITY_SEARCH_RESULTS_UPDATED")
        f:RegisterEvent("AUCTION_HOUSE_THROTTLED_MESSAGE_DROPPED")
        f:RegisterEvent("AUCTION_HOUSE_THROTTLED_MESSAGE_QUEUED")
    elseif event == "AUCTION_HOUSE_SHOW" then
        -- let blizz's own frame send its first queries b4 we pile on
        C_Timer.After(2, start)
        if ticker then
            ticker:Cancel()
        end
        ticker = C_Timer.NewTicker(WATCH_EVERY_S, watchTick)
        C_Timer.After(1, function()
            local ok, err = pcall(recordDeposits)
            if not ok then
                say("|cffff4040deposits failed|r: %s", tostring(err))
            end
        end)
    elseif event == "AUCTION_HOUSE_CLOSED" then
        -- walking away from th AH is th natural moment 2 save, whatever th data's age
        C_Timer.After(0.5, function()
            remind(true)
        end)
        if ticker then
            ticker:Cancel()
            ticker = nil
        end
        watch.pending = nil
    elseif event == "COMMODITY_SEARCH_RESULTS_UPDATED" then
        watchRead(arg)
    elseif event == "REPLICATE_ITEM_LIST_UPDATE" then
        if not scan then
            return
        end
        local s = scan
        if #s.events == 0 and not s.reread then
            db.last_dump = s.server_time
        end
        s.events[#s.events + 1] = { ms = elapsed(), n = C_AuctionHouse.GetNumReplicateItems() }
        -- it re-fires as item info trickles in, so a busy AH may never go quiet. cap it
        if #s.events == 1 then
            C_Timer.After(MAX_SETTLE_S, function()
                if scan == s and not s.rows then
                    s.forced = true
                    finish()
                end
            end)
        end
        gen = gen + 1
        local mine = gen
        C_Timer.After(QUIET_S, function()
            if gen == mine and scan == s and not s.rows then
                finish()
            end
        end)
    elseif scan then
        scan.throttle[#scan.throttle + 1] = { event = event, ms = elapsed() }
    end
end)

SLASH_FOREVERSCAN1 = "/fscan"
SlashCmdList.FOREVERSCAN = function(msg)
    local cmd, rest = msg:match("^watch%s*(%S*)%s*(.*)$")
    if cmd then
        local item = itemArg(rest)
        if cmd == "" then
            db.watch_on = not db.watch_on
            say("watch %s, %d items, %d polls saved", db.watch_on and "on" or "off", #db.watchlist, #db.watch_polls)
        elseif cmd == "add" and item then
            if not tContains(db.watchlist, item) then
                table.insert(db.watchlist, item)
            end
            say("watching %d (%d items, each ~every %ds)", item, #db.watchlist, #db.watchlist * WATCH_EVERY_S)
        elseif cmd == "del" and item then
            tDeleteItem(db.watchlist, item)
            say("dropped %d (%d items)", item, #db.watchlist)
        elseif cmd == "list" then
            for _, id in ipairs(db.watchlist) do
                say("%d %s", id, itemName(id))
            end
        else
            say("/fscan watch [add|del <id or shift-click>|list]")
        end
    elseif msg == "read" then
        -- re-read whatever th client still holds from th last dump, no new request so no 15 min wait
        if scan then
            say("already scanning")
        elseif C_AuctionHouse.GetNumReplicateItems() == 0 then
            say("nothing held, needs a fresh dump")
        else
            scan = { t0 = debugprofilestop(), server_time = now(), character = UnitName("player"),
                     reread = true, events = {}, throttle = {} }
            finish()
        end
    elseif msg == "status" then
        for i, s in ipairs(db.scans) do
            say("#%d %s: %s listings, %d events%s", i, date("%m-%d %H:%M", s.server_time), tostring(s.n),
                #s.events, s.timed_out and ", TIMED OUT" or s.error and (", FAILED " .. s.error) or "")
        end
        local priced = 0
        for _ in pairs(db.deposits) do
            priced = priced + 1
        end
        say("deposits known 4 %d items", priced)
        local last_poll = db.watch_polls[#db.watch_polls]
        say("watch %s%s, %d polls saved, last %s", db.watch_on and "on" or "off",
            ticker and (watchSafe() and " nd polling" or " but paused on this screen") or "", #db.watch_polls,
            last_poll and ("%ds ago (%s: %d listings, %d ms)"):format(now() - last_poll.t,
                itemName(last_poll.item), last_poll.n, last_poll.ms) or "never")
        if scan then
            local last = scan.events[#scan.events]
            say("in flight, %d ms, %d update events, %d listings so far, last update %s ms", elapsed(),
                #scan.events, C_AuctionHouse.GetNumReplicateItems(), last and last.ms or "-")
        end
    elseif not AuctionHouseFrame or not AuctionHouseFrame:IsShown() then
        say("open th AH first")
    else
        start(msg == "force")
    end
end
