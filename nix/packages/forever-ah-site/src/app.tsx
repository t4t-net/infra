import { useEffect, useRef, useState } from 'preact/hooks'
import type { ComponentChildren } from 'preact'
import { TransFlag } from './TransFlag'
import { SparkleFrame } from './Sparkles'
import { KaomojiRain } from './KaomojiRain'
import { Starfield } from './Starfield'
import { Nyan } from './Nyan'
// filled by main.tsx from data.json before the first render; forever-ah export rewrites it hourly
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export let D: any
export const setData = (d: unknown) => { D = d }

const theme = 'gold'

// ---- text cells for the aut-num style blocks: plain strings or colored runs, padded by visible length
type Run = { t: string; c?: string; href?: string; external?: boolean }
type Cell = string | Run[]
// every item links 2 its wowhead page, in its rarity color
const item = (id: number, name: string): Run[] =>
  [{ t: name, c: `item q-${D.quality[id] ?? 'common'}`, href: `https://www.wowhead.com/forever/item=${id}`, external: true }]
// recipes link 2 their spell (th recipe tooltip, w reagents), colored by wat they make
const recipe = (r: Craft): Run[] => r.spell
  ? [{ ...item(r.out.id, r.recipe)[0], href: `https://www.wowhead.com/forever/spell=${r.spell}` }]
  : item(r.out.id, r.recipe)
const runs = (x: Cell): Run[] => (typeof x === 'string' ? [{ t: x }] : x)
const width = (x: Cell) => runs(x).reduce((a, r) => a + [...r.t].length, 0)

function money(c: number | null | undefined): Run[] {
  if (c == null) return [{ t: '-', c: 'c' }]
  const neg = c < 0
  c = Math.round(Math.abs(c))
  const g = Math.floor(c / 10000), s = Math.floor(c / 100) % 100, cp = c % 100
  const out: Run[] = []
  if (g) out.push({ t: `${g}g`, c: 'gold' })
  if (s || (g && cp)) out.push({ t: `${out.length ? ' ' : ''}${s}s`, c: 'silver' })
  if (cp || !out.length) out.push({ t: `${out.length ? ' ' : ''}${cp}c`, c: 'copper' })
  if (neg) out.unshift({ t: '-' })
  return out
}

function trend(now?: number | null, then?: number | null): Run[] {
  if (!now || !then) return [{ t: '-', c: 'c' }]
  const p = Math.round((now / then - 1) * 100)
  if (Math.abs(p) < 3) return [{ t: 'flat', c: 'c' }]
  return [{ t: `${p > 0 ? '+' : ''}${p}%`, c: p < 0 ? 'down' : undefined }]
}

// sales we're sure of, then th ones a cancel wud have looked th same as. never folded into one number: an
// overconfident count misleads whoever acts on it
function sold(m: Market): Cell {
  if (m.sold == null) return [{ t: '-', c: 'c' }]
  return [{ t: m.sold.toLocaleString() }, ...(m.sold_maybe ? [{ t: ` (+${m.sold_maybe.toLocaleString()}?)`, c: 'c' }] : [])]
}

// how old th book behind a row is, worked out when th page is LOOKED at, not when it was exported: "live" is
// th addon watching it in th last 15 min, anything older is th hourly api (or a stale poll) nd says so
function seen(m: Market): Run[] {
  if (m.as_of == null) return [{ t: '-', c: 'c' }]
  const age = Date.now() / 1000 - m.as_of
  if (age < 15 * 60) return [{ t: 'live', c: 'gold' }]
  return [{ t: age < 3600 ? `${Math.round(age / 60)}m` : age < 48 * 3600 ? `${Math.round(age / 3600)}h` : `${Math.round(age / 86400)}d`, c: 'c' }]
}

// how th deposit math wants it listed, nd which way sold prices r heading
function plan(m: Market): Run[] {
  const out: Run[] = []
  if (m.duration_h) out.push({ t: ` · list ${m.duration_h}h, ` }, ...(m.deposit_known ? money(m.listing_deposit) : [{ t: '~' }, ...money(m.listing_deposit), { t: ' (guess)' }]), { t: ' deposit' })
  if (m.trend_per_h && Math.abs(m.trend_per_h) >= 1) out.push({ t: ' · sold prices ' }, ...money(m.trend_per_h), { t: '/h', c: m.trend_per_h < 0 ? 'down' : undefined })
  return out
}

// how long until urs sells as th cheapest listing; "slow" means none sold while we watched. "ahead" is th
// queue u join when th floor is at th ah's minimum nd cant be undercut
function wait(m: Market): Run[] {
  const q: Run[] = m.ahead ? [{ t: `, ${m.ahead.toLocaleString()} ahead`, c: 'down' }] : []
  if (m.sold == null) return [{ t: '-', c: 'c' }, ...q]
  if (!m.wait_h) return [{ t: 'slow', c: 'down' }, ...q]
  const h = m.wait_h
  const t = h < 1 ? `~${Math.max(1, Math.round(h * 60))}m` : h < 48 ? `~${Math.round(h)}h` : `~${Math.round(h / 24)}d`
  return [{ t, c: h > 12 ? 'down' : undefined }, ...q]
}

function Runs({ cell }: { cell: Cell }) {
  return <>{runs(cell).map(r =>
    r.href ? <a href={r.href} className={r.c} {...(r.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>{r.t}</a>
      : r.c ? <span className={r.c}>{r.t}</span> : r.t)}</>
}

// right-aligned columns are numbers; the first column is always left-aligned
function Block({ head, rows, notes }: { head: string[]; rows: Cell[][]; notes?: Run[][] }) {
  const w = head.map((h, i) => Math.max([...h].length, ...rows.map(r => width(r[i]))))
  const pad = (cell: Cell, i: number) => {
    const n = w[i] - width(cell)
    return i === 0 ? <><Runs cell={cell} />{' '.repeat(n)}</> : <>{' '.repeat(n)}<Runs cell={cell} /></>
  }
  const line = (cells: Cell[]) => cells.map((c, i) => <>{i ? '  ' : ''}{pad(c, i)}</>)
  return (
    <pre>
      <span className="c">{line(head.map(h => h))}</span>{'\n'}
      {rows.map((r, k) => <>{line(r)}{notes?.[k] ? <span className="c">{'\n  # '}<Runs cell={notes[k]} /></span> : null}{'\n'}</>)}
    </pre>
  )
}

type Market = { id: number; name: string; wait_h: number | null; ahead: number; deposit_risk: number | null; floor: number | null; median: number | null; qty: number | null; listings: number | null; floor_then: number | null; sold: number | null; sold_at: number | null; vendor: number | null
  sold_maybe: number | null; as_of: number | null; source: 'api' | 'watch' | null; duration_h: number | null; listing_deposit: number | null; deposit_known: boolean; trend_per_h: number | null }
type Farm = { cost: number; profit: number; mats: { id: number; name: string; qty: number; src: 'farm' | 'ah' | 'vendor' }[] }
type Craft = { recipe: string; spell: number | null; makes: number; cost: number; revenue: number; profit: number; mats: { id: number; name: string; qty: number; vendor?: boolean }[]; out: Market; farm?: Farm }

function Crafts({ rows }: { rows: Craft[] }) {
  if (!rows.length) return <p className="mute">nothing here clears a profit right now.</p>
  return (
    <Block
      head={['recipe', 'mats', 'sells', 'profit', 'listed', `${D.hours}h`, 'sold', 'sold at', 'wait', 'seen']}
      rows={rows.map(r => [
        [...recipe(r), ...(r.makes > 1 ? [{ t: ` x${r.makes}`, c: 'c' }] : [])], money(r.cost), money(r.revenue), money(r.profit),
        String(r.out.listings ?? 0), trend(r.out.floor, r.out.floor_then), sold(r.out),
        money(r.out.sold_at), wait(r.out), seen(r.out),
      ])}
      notes={rows.map(r => [...r.mats.flatMap((m, i) => [{ t: `${i ? ', ' : ''}${m.qty} ` }, ...item(m.id, m.name), ...(m.vendor ? [{ t: ' (vendor)' }] : [])]), ...plan(r.out)])}
    />
  )
}

// same crafts, but gathered mats cost nothing; vs raw is wat crafting earns over just selling those mats
function FarmCrafts({ rows }: { rows: Craft[] }) {
  if (!rows.length) return <p className="mute">nothing here clears a profit right now.</p>
  return (
    <Block
      head={['recipe', 'buy', 'sells', 'profit', 'vs raw', 'listed', 'wait', 'seen']}
      rows={rows.map(r => [
        [...recipe(r), ...(r.makes > 1 ? [{ t: ` x${r.makes}`, c: 'c' }] : [])], money(r.farm!.cost), money(r.revenue), money(r.farm!.profit),
        money(r.profit), String(r.out.listings ?? 0), wait(r.out), seen(r.out),
      ])}
      notes={rows.map(r => [...r.farm!.mats.flatMap((m, i) => [{ t: `${i ? ', ' : ''}${m.qty} ` }, ...item(m.id, m.name), ...(m.src !== 'farm' ? [{ t: ` (${m.src})` }] : [])]), ...plan(r.out)])}
    />
  )
}

function Mats({ rows }: { rows: Market[] }) {
  return (
    <Block
      head={['item', 'cheapest', 'median', `${D.hours}h`, 'on ah', 'sold', 'wait', 'vendor', 'seen']}
      rows={rows.map(m => [
        item(m.id, m.name), money(m.floor), money(m.median), trend(m.floor, m.floor_then), (m.qty ?? 0).toLocaleString(),
        sold(m), wait(m), m.vendor ? money(m.vendor) : [{ t: '-', c: 'c' }], seen(m),
      ])}
    />
  )
}

const PROFS = ['mining', 'herbalism', 'skinning', 'blacksmithing', 'engineering', 'tailoring', 'leatherworking', 'alchemy', 'enchanting', 'cooking'] as const
const VIEWS = ['meta', 'quests', ...PROFS, 'flips'] as const
type View = typeof VIEWS[number]

const TAKES: Record<string, string> = {
  mining: `best thing to have on a fresh character right now. everyone's leveling a crafting profession at once, so raw mats sell constantly and most crafted stuff doesn't. gems from veins are free money at every tier. only smelt where the bar beats the ore, or while it still gives you skill.`,
  herbalism: `alchemists and cooks buy these. same launch pattern as ore: the low tiers flood, and anything that needs real skill is scarce and pricey for now.`,
  skinning: `leather feeds leatherworking and a lot of blacksmithing and engineering. check the hides separately, they don't track the leather. cloth is down here too since it drops on its own.`,
  blacksmithing: `the forever-only skyforged plans (nightclaw druids rep, bs 50-60) turn five copper bars into 20-40s, but they sell slowly, about one an hour for the best piece. stones and rods move steadily. most low-level gear sells for less than its bars.`,
  engineering: `the money is in stuff that gets used up and the parts other engineers need to level: scopes, fireworks, bombs, tubes, struts, casings. margins are big and sliding fast as more people hit 200.`,
  tailoring: `no gathering profession needed, cloth just drops. cheap mats, lots of competition.`,
  leatherworking: `pairs with skinning. armor kits and the odd crafted piece are where the margins are.`,
  alchemy: `potions and oils get used up, so demand never goes away. expect a spike before raids open on dec 9.`,
  enchanting: `enchants are services, not items, so they never touch the ah. this only covers what enchanters make as items: rods, wands, oils.`,
  cooking: `secondary profession, small money. buff food matters once raids open.`,
}

const QA: { q: string; a: string }[] = [
  {
    q: 'how do you know what actually sold?',
    a: `every listing has an id and a time-left bucket. if an id disappears between two hourly dumps while it still had hours left, and no cheaper listing from that same dump is still up, somebody bought it. if a cheaper one is still sitting there, the vanished one was pulled (cancelled or reposted), since buyers take the cheapest first. a cancel right at the floor still sneaks in as a sale.`,
  },
  {
    q: 'why is a craft i know about missing?',
    a: `crafts whose market is just sellers undercutting each other get hidden: three or more units pulled and reposted for every one bought, or no sales at all in the last three dumps when the day's pace says there should have been a handful. the profit math on those is fiction, nobody's buying at the floor.`,
  },
  {
    q: 'how fresh is this?',
    a: `blizzard publishes a new dump about once an hour and this page regenerates a few minutes after each one. trends and sales cover the window in the header.`,
  },
  {
    q: 'how do you know which auction house is mine?',
    a: `the api calls five different houses "alliance auction house". price fingerprinting pointed at three of them, so we listed one rough stone at 12g 34s 56c and waited for it to show up. house 111.`,
  },
  {
    q: 'can i trust a big margin?',
    a: `look at the listed column first. a +2g craft with 8 listings might sit for days, and launch-week prices are sliding fast, so check the trend column too. post a couple, see what sells, then scale up.`,
  },
]

function useView(): View {
  const get = (): View => {
    const v = location.hash.slice(1)
    return (VIEWS as readonly string[]).includes(v) ? (v as View) : 'meta'
  }
  const [view, setView] = useState(get)
  useEffect(() => {
    const on = () => setView(get())
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  return view
}

const when = (t: number) =>
  new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).toLowerCase()

function Section({ title, children }: { title: string; children: ComponentChildren }) {
  return <section><h2>{title}</h2>{children}</section>
}

// ---- quests: questie's levels, givers nd chains + blizzard's rewards, priced against th ah
type Reward = { id: number; name: string; q: string; ah: number | null; vendor: number | null; value: number }
type Quest = {
  id: number; name: string; zone: string; req: number | null; lvl: number | null; type: string | null
  starts: { name: string; x: number | null; y: number | null }[]; pre: number[]; next: number | null; rep: boolean
  xp: number | null; money: number | null; choice: Reward[]; fixed: Reward[]
}

// th game's quest log colors, relative 2 ur level (classic's grey cutoff)
function con(lvl: number | null, me: number): string {
  if (lvl == null) return 'c'
  const grey = me <= 5 ? 0 : me < 40 ? me - Math.floor(me / 10) - 5 : me - Math.floor(me / 5) - 1
  const d = lvl - me
  return d >= 5 ? 'con-red' : d >= 3 ? 'con-orange' : d >= -2 ? 'con-yellow' : lvl > grey ? 'con-green' : 'con-grey'
}

function stored<T>(key: string, init: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try { const s = localStorage.getItem(key); return s == null ? init : JSON.parse(s) } catch { return init }
  })
  return [v, (x: T) => { setV(x); try { localStorage.setItem(key, JSON.stringify(x)) } catch {} }]
}

function Quests() {
  const [all, setAll] = useState<Quest[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [zone, setZone] = stored('quest-zone', 'Loch Modan')
  const [me, setMe] = stored('quest-level', 15)
  useEffect(() => {
    fetch('quests.json', { cache: 'no-store' })
      .then(r => {
        // a missing file comes back as an html 404 page, which r.json() would choke on
        if (r.status === 404) throw new Error('not exported yet, the next hourly update at :20 writes it')
        if (!r.ok) throw new Error(`quests.json: ${r.status}`)
        return r.json()
      })
      .then(d => setAll(d.quests)).catch(e => setErr(e instanceof Error ? e.message : String(e)))
  }, [])
  if (err) return <Section title="quests"><p className="mute">no quests yet: {err}.</p></Section>
  if (!all) return <Section title="quests"><p className="mute">loading quests...</p></Section>

  const byId = new Map(all.map(q => [q.id, q]))
  const zones = [...new Set(all.map(q => q.zone))].sort()
  const here = all.filter(q => q.zone === zone && (q.req ?? 0) <= me)
    .sort((a, b) => (a.lvl ?? 999) - (b.lvl ?? 999) || (a.req ?? 0) - (b.req ?? 0) || a.name.localeCompare(b.name))
  const later = all.filter(q => q.zone === zone && (q.req ?? 0) > me).length
  const best = (q: Quest) => [...q.choice, ...q.fixed].sort((a, b) => b.value - a.value)[0]
  const quest = (q: Quest): Run[] => [{ t: q.name, c: con(q.lvl, me), href: `https://www.wowhead.com/forever/quest=${q.id}`, external: true }]

  return (
    <Section title="quests">
      <p>
        every quest alliance can do, from questie's database (levels, givers, chains) and blizzard's own
        (xp, money, rewards). colors match your quest log. reward value is whichever is more: undercutting the
        ah, or vendoring it.
      </p>
      <div className="pickers">
        <label>zone <select value={zone} onChange={e => setZone((e.target as HTMLSelectElement).value)}>
          {zones.map(z => <option key={z} value={z}>{z}</option>)}
        </select></label>
        <label>your level <input type="number" min={1} max={60} value={me}
          onInput={e => setMe(Math.max(1, Math.min(60, Number((e.target as HTMLInputElement).value) || 1)))} /></label>
      </div>
      {here.length ? <Block
        head={['lvl', 'quest', 'xp', 'money', 'best reward', 'giver']}
        rows={here.map(q => {
          const b = best(q), g = q.starts[0]
          return [
            [{ t: q.lvl == null ? '?' : String(q.lvl), c: con(q.lvl, me) }],
            quest(q),
            q.xp ? q.xp.toLocaleString() : [{ t: '-', c: 'c' }],
            q.money ? money(q.money) : [{ t: '-', c: 'c' }],
            b ? [...item(b.id, b.name).map(r => ({ ...r, c: `item q-${b.q}` })), { t: ' ' }, ...money(b.value)] : [{ t: '-', c: 'c' }],
            g ? `${g.name}${g.x != null ? ` ${Math.round(g.x)},${Math.round(g.y ?? 0)}` : ''}` : [{ t: '?', c: 'c' }],
          ]
        })}
        notes={here.map(q => {
          const bits: Run[] = []
          const add = (r: Run[]) => { if (bits.length) bits.push({ t: ' · ' }); bits.push(...r) }
          if (q.type && q.type !== 'Normal') add([{ t: q.type.toLowerCase() }])
          if (q.pre.length) add([{ t: 'after ' }, ...q.pre.slice(0, 2).flatMap((p, i) => [...(i ? [{ t: ' or ' }] : []), { t: byId.get(p)?.name ?? `quest ${p}` }])])
          if (q.next) add([{ t: 'leads to ' }, { t: byId.get(q.next)?.name ?? `quest ${q.next}` }])
          if (q.choice.length > 1) add([{ t: 'pick: ' }, ...q.choice.flatMap((c, i) => [...(i ? [{ t: ', ' }] : []), ...item(c.id, c.name).map(r => ({ ...r, c: `item q-${c.q}` })), { t: ` ${Math.round(c.value / 100)}s` }])])
          if (q.lvl == null) add([{ t: 'new in forever, level unknown' }])
          return bits
        })}
      /> : <p className="mute">nothing in {zone} at level {me} yet.</p>}
      {later > 0 && <p className="note">{later} more {zone} quests need a higher level.</p>}
    </Section>
  )
}

function ViewBody({ view }: { view: View }) {
  if (view === 'quests') return <Quests />
  const crafts = D.crafts as Record<string, { count: number; priced: number; losers: number; wars?: number; top: Craft[]; starters: Craft[]; farmed?: Craft[] }>
  const gather = D.gather as Record<string, Market[]>

  if (view === 'meta') {
    const best = Object.entries(crafts).filter(([, v]) => v.top.length)
    const farmed = Object.entries(crafts).filter(([, v]) => v.farmed?.length)
    return (
      <Section title="the meta">
        <pre>{`early-game:   `}<a href="#mining">gather</a>{` and sell raw, gems too     `}<span className="c"># mats outsell crafts in launch week</span>{`
skill-ups:    craft whatever loses least      `}<span className="c"># most low-level gear sells under its mats</span>{`
mid-game:     consumables + parts             `}<span className="c"># </span><a href="#engineering">engineering</a><span className="c">, </span><a href="#alchemy">alchemy</a>{`
capital:      buy in blackwater, sell here    `}<span className="c"># </span><a href="#flips">flips</a>{`
raid-launch:  stones, flasks, thorium         `}<span className="c"># raids open dec 9</span></pre>
        <h3>best craft per profession right now, buying mats</h3>
        <Block
          head={['profession', 'recipe', 'profit', 'listed']}
          rows={best.map(([k, v]) => [[{ t: k, href: `#${k}` }], recipe(v.top[0]), money(v.top[0].profit), String(v.top[0].out.listings ?? 0)])}
        />
        <h3>best craft per profession, farming mats yourself</h3>
        <Block
          head={['profession', 'recipe', 'profit', 'vs raw', 'listed']}
          rows={farmed.map(([k, v]) => [[{ t: k, href: `#${k}` }], recipe(v.farmed![0]), money(v.farmed![0].farm!.profit), money(v.farmed![0].profit), String(v.farmed![0].out.listings ?? 0)])}
        />
        <p className="note">vs raw is what crafting earns on top of just selling the mats you gathered. if it's negative, sell the mats instead.</p>
        <p className="note">prices move fast, especially for anything only a few people can make yet. read the trend column before you commit to anything.</p>
      </Section>
    )
  }

  if (view === 'flips') {
    return (
      <Section title="flips">
        <p>
          alliance players can use the blackwater house too, and it's much quieter, so things get listed cheap there.
          buy in blackwater, sell here where the buyers are. the other direction looks great on paper and never sells.
          assumes a 15% cut on the neutral side.
        </p>
        <p>
          most spreads only last an hour, and by the time you're at the ah they're gone. the open column counts how
          many of the last {D.dumps} dumps each one was open for. plan trips around the ones that are open nearly
          every time.
        </p>
        <Block
          head={['item', 'blackwater', 'here', 'profit', 'open']}
          rows={(D.flips as { id: number; name: string; buy: number; buy_listings: number; sell: number; sell_listings: number; profit: number; open: number }[]).map(f => [
            item(f.id, f.name), [...money(f.buy), { t: ` (${f.buy_listings})`, c: 'c' }], [...money(f.sell), { t: ` (${f.sell_listings})`, c: 'c' }], money(f.profit),
            [{ t: `${f.open}/${D.dumps}`, c: f.open * 2 < D.dumps ? 'c' : undefined }],
          ])}
        />
        <h3>under vendor price</h3>
        <p>
          listed for less than a vendor pays, so buy it and sell it to any vendor. gear can only be listed in whole
          silvers, so when sellers undercut a wall at 4s they land on 3s even if it vendors for 3s 7c. most of these
          are a few copper each and get sniped within the hour; the open column counts the dumps in a row it's been
          up. under is how many are below vendor, when we track that item's listings.
        </p>
        <Block
          head={['item', 'listed', 'vendor', 'profit', 'under', 'open']}
          rows={((D.vendor ?? []) as { id: number; name: string; floor: number; vendor: number; profit: number; under: number | null; listings: number; open: number }[]).map(v => [
            item(v.id, v.name), money(v.floor), money(v.vendor), money(v.profit),
            [{ t: v.under == null ? '-' : String(v.under), c: 'c' }], [{ t: `${v.open}/${D.dumps}`, c: 'c' }],
          ])}
        />
      </Section>
    )
  }

  const c = crafts[view], g = gather[view]
  return (
    <Section title={view}>
      <p>{TAKES[view]}</p>
      {g && <><h3>raw mats</h3><Mats rows={g} /></>}
      {view === 'skinning' && <><h3>cloth</h3><Mats rows={gather.cloth} /></>}
      {c && <>
        <h3>crafts that clear a profit, buying mats off the ah</h3>
        <Crafts rows={c.top} />
        {c.starters.length > 0 && <><h3>cheap ones, under 25s in mats</h3><Crafts rows={c.starters} /></>}
        {c.farmed && <>
          <h3>if you farm the mats yourself</h3>
          <p className="note">
            gathered mats count as free, bars get smelted from your own ore. vendor mats and anything you can't
            gather (dust, drops, other professions' parts) still get bought. vs raw is what the craft earns over
            just selling those mats, so a negative one means sell the mats instead.
          </p>
          <FarmCrafts rows={c.farmed} />
        </>}
        <p className="note">{c.count} recipes, {c.priced} with a real market, {c.losers} of those sell for less than their mats.{c.wars ? ` ${c.wars} more hidden for being relisting wars.` : ''}</p>
      </>}
    </Section>
  )
}

export function App() {
  // shared so the starfield can keep its stars clear of the sparkle border
  const frameRef = useRef<HTMLDivElement>(null)
  const view = useView()

  return (
    <>
    <Starfield theme={theme} frameRef={frameRef} />
    <KaomojiRain theme={theme} />
    <Nyan theme={theme} />
    <main>
      <SparkleFrame frameRef={frameRef}>
        <header>
          <div className="flag"><TransFlag theme={theme} /></div>
          <div className="intro">
            <h1>forever gold meta</h1>
            <dl className="facts">
              <dt>game</dt><dd>wow: forever</dd>
              <dt>house</dt><dd>111, normal, alliance</dd>
              <dt>window</dt><dd>{D.dumps} dumps over {D.hours}h</dd>
              {/* th api dump is hourly; watched items can b fresher, nd th header shudnt undersell or blur tht */}
              <dt>api dump</dt><dd>{when(D.dump)} <span className="c">(hourly)</span></dd>
              {D.watch_as_of ? <><dt>live</dt><dd>{when(D.watch_as_of)} <span className="c">(addon, {D.watch_items} items)</span></dd></> : null}
              <dt>source</dt><dd>battle.net api{D.watch_as_of ? ' + ForeverScan addon' : ''}</dd>
            </dl>
          </div>
        </header>

        <section>
          <p>
            what actually makes gold in wow: forever, worked out from blizzard's
            own auction house data instead of vibes. every hour a box in our
            rack pulls every auction house dump, keeps the prices, and follows
            individual listings so we can tell what sold from what just sat there.
          </p>
          <p>
            everything here is one house. prices assume you buy mats off the ah, except the
            farm-it-yourself tables, and sell by undercutting the cheapest listing, after the 5% cut. listing costs a 1s
            deposit you only get back if it sells, so profit also subtracts the deposits you'd expect
            to lose relisting a slow seller until it goes (up to two weeks of it). wait is roughly how
            long until yours sells. gear and other non-stacking items can't be listed under 1s, so
            once the cheapest one is at 1s you can't undercut, and you wait behind everyone already there.
          </p>
        </section>

        <nav className="views" aria-label="professions">
          {VIEWS.map(v => <a key={v} href={`#${v}`} aria-current={view === v ? 'page' : undefined}>{v}</a>)}
        </nav>

        <ViewBody view={view} />

        <section>
          <h2>q&amp;a</h2>
          {QA.map(({ q, a }) => (
            <dl className="qa" key={q}>
              <dt>q:</dt><dd className="q">{q}</dd>
              <dt>a:</dt><dd>{a}</dd>
            </dl>
          ))}
        </section>

        <footer>
          <p>
            made by <a href="https://catmod.ing">catmod.ing</a> &amp; luna the trans puppygirl
          </p>
          <p>
            not affiliated with blizzard. buy low, sell high, pet your cat.
          </p>
        </footer>
      </SparkleFrame>
    </main>
    </>
  )
}
