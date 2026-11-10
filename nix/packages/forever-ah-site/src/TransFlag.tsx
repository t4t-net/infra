import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'

// 10 rows of 1em vs cells ~0.6em wide: 28 cols lands near the real 5:3 ratio
const MAX_FLAG_COLS = 28
const FLAG_ROWS = 10
const MAX_AMP = 2
const RENDER_ROWS = FLAG_ROWS + MAX_AMP
const FREQ = 0.6
const SPEED = 2.5
const POLE_CHARS = 2

function colsFromWidth(w: number, charW: number) {
  return Math.max(10, Math.min(MAX_FLAG_COLS, Math.floor(w / charW) - POLE_CHARS))
}

// measure a real glyph in the inherited font instead of guessing its width
export function measureCharWidth(el: HTMLElement, glyph = '█') {
  const probe = document.createElement('span')
  probe.textContent = glyph.repeat(10)
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre'
  el.appendChild(probe)
  const w = probe.getBoundingClientRect().width / 10
  probe.remove()
  return w || 9
}

function useResponsiveCols() {
  const ref = useRef<HTMLDivElement>(null)
  const [cols, setCols] = useState(MAX_FLAG_COLS)

  // layout effect so the first measurement lands before paint, not one frame late
  useLayoutEffect(() => {
    const el = ref.current
    const parent = el?.parentElement
    if (!el || !parent) return
    const charW = measureCharWidth(el)
    const update = (w: number) => setCols(colsFromWidth(w, charW))
    update(parent.getBoundingClientRect().width)
    const obs = new ResizeObserver(entries => update(entries[0].contentRect.width))
    obs.observe(parent)
    return () => obs.disconnect()
  }, [])

  return { cols, ref }
}

export const FLAG_COLORS: Record<string, string[]> = {
  // bronze-gold-bronze guild banner for the gold meta page
  gold:     ['#7a4f24', '#c8815a', '#e8c15a', '#c8815a', '#7a4f24'],
  trans:    ['#5BCEFA', '#F5A9B8', '#FFFFFF', '#F5A9B8', '#5BCEFA'],
  lesbian:  ['#D62900', '#FF9B55', '#FFFFFF', '#D461A6', '#A50062'],
  bisexual: ['#D60270', '#D60270', '#9B4F96', '#0038A8', '#0038A8'],
  nonbinary:['#FCF434', '#FCF434', '#FFFFFF', '#9C59D1', '#2D2D2D'],
}

type Props = { theme: string }

export function TransFlag({ theme }: Props) {
  const [time, setTime] = useState(0)
  const { cols, ref } = useResponsiveCols()
  const stripes = FLAG_COLORS[theme] ?? FLAG_COLORS.trans

  useEffect(() => {
    const id = setInterval(() => setTime(t => t + 0.05), 40)
    return () => clearInterval(id)
  }, [])

  const rows: (string | null)[][] = []
  for (let r = 0; r < RENDER_ROWS; r++) {
    const cells: (string | null)[] = []
    for (let c = 0; c < cols; c++) {
      const amp = MAX_AMP * (c / (cols - 1))
      const disp = amp * Math.sin(FREQ * c - SPEED * time)
      const stripeR = r - disp
      if (stripeR >= 0 && stripeR < FLAG_ROWS) {
        const stripeIdx = Math.max(0, Math.min(4, Math.floor(stripeR / 2)))
        cells.push(stripes[stripeIdx])
      } else {
        cells.push(null)
      }
    }
    rows.push(cells)
  }

  return (
    <div ref={ref} style={{ lineHeight: '1em', userSelect: 'none' }}>
      {rows.map((row, r) => (
        <div key={r} style={{ display: 'flex' }}>
          <span style={{ color: '#555' }}>||</span>
          {row.map((color, c) => (
            <span key={c} style={{ color: color ?? 'transparent' }}>█</span>
          ))}
        </div>
      ))}
    </div>
  )
}
