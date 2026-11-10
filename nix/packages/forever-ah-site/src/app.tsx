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

type Market = { id: number; name: string; floor: number | null; median: number | null; qty: number | null; listings: number | null; floor_then: number | null; sold: number | null; vendor: number | null }
type Craft = { recipe: string; spell: number | null; makes: number; cost: number; revenue: number; profit: number; mats: { id: number; name: string; qty: number; vendor?: boolean }[]; out: Market }

function Crafts({ rows }: { rows: Craft[] }) {
  if (!rows.length) return <p className="mute">nothing here clears a profit right now.</p>
  return (
    <Block
      head={['recipe', 'mats', 'sells', 'profit', 'listed', `${D.hours}h`, 'sold']}
      rows={rows.map(r => [
        [...recipe(r), ...(r.makes > 1 ? [{ t: ` x${r.makes}`, c: 'c' }] : [])], money(r.cost), money(r.revenue), money(r.profit),
        String(r.out.listings ?? 0), trend(r.out.floor, r.out.floor_then), r.out.sold == null ? [{ t: '-', c: 'c' }] : String(r.out.sold),
      ])}
      notes={rows.map(r => r.mats.flatMap((m, i) => [{ t: `${i ? ', ' : ''}${m.qty} ` }, ...item(m.id, m.name), ...(m.vendor ? [{ t: ' (vendor)' }] : [])]))}
    />
  )
}

function Mats({ rows }: { rows: Market[] }) {
  return (
    <Block
      head={['item', 'cheapest', 'median', `${D.hours}h`, 'on ah', 'sold', 'vendor']}
      rows={rows.map(m => [
        item(m.id, m.name), money(m.floor), money(m.median), trend(m.floor, m.floor_then), (m.qty ?? 0).toLocaleString(),
        m.sold == null ? [{ t: '-', c: 'c' }] : m.sold.toLocaleString(), m.vendor ? money(m.vendor) : [{ t: '-', c: 'c' }],
      ])}
    />
  )
}

const PROFS = ['mining', 'herbalism', 'skinning', 'blacksmithing', 'engineering', 'tailoring', 'leatherworking', 'alchemy', 'enchanting', 'cooking'] as const
const VIEWS = ['meta', ...PROFS, 'flips'] as const
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
    a: `every listing has an id and a time-left bucket. if an id disappears between two hourly dumps while it still had hours left, and it was priced at or under the next dump's cheapest listing, somebody bought it. anything pricier that vanished was a cancel or a repost, since buyers take the cheapest first. it still overcounts a little.`,
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

function ViewBody({ view }: { view: View }) {
  const crafts = D.crafts as Record<string, { count: number; priced: number; losers: number; top: Craft[]; starters: Craft[] }>
  const gather = D.gather as Record<string, Market[]>

  if (view === 'meta') {
    const best = Object.entries(crafts).filter(([, v]) => v.top.length)
    return (
      <Section title="the meta">
        <pre>{`early-game:   `}<a href="#mining">gather</a>{` and sell raw, gems too     `}<span className="c"># mats outsell crafts in launch week</span>{`
skill-ups:    craft whatever loses least      `}<span className="c"># most low-level gear sells under its mats</span>{`
mid-game:     consumables + parts             `}<span className="c"># </span><a href="#engineering">engineering</a><span className="c">, </span><a href="#alchemy">alchemy</a>{`
capital:      buy in blackwater, sell here    `}<span className="c"># </span><a href="#flips">flips</a>{`
raid-launch:  stones, flasks, thorium         `}<span className="c"># raids open dec 9</span></pre>
        <h3>best craft per profession right now</h3>
        <Block
          head={['profession', 'recipe', 'profit', 'listed']}
          rows={best.map(([k, v]) => [[{ t: k, href: `#${k}` }], recipe(v.top[0]), money(v.top[0].profit), String(v.top[0].out.listings ?? 0)])}
        />
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
        <h3>crafts that clear a profit</h3>
        <Crafts rows={c.top} />
        {c.starters.length > 0 && <><h3>cheap ones, under 25s in mats</h3><Crafts rows={c.starters} /></>}
        <p className="note">{c.count} recipes, {c.priced} with a real market, {c.losers} of those sell for less than their mats.</p>
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
              <dt>latest</dt><dd>{when(D.dump)}</dd>
              <dt>source</dt><dd>battle.net api</dd>
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
            everything here is one house. prices assume you buy mats off the ah
            and sell by undercutting the cheapest listing, after the 5% cut.
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
