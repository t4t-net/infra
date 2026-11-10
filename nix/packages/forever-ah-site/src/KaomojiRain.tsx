import { useEffect, useState } from 'preact/hooks'
import { FLAG_COLORS } from './TransFlag'

// latin-1/greek/geometric only: halfwidth katakana renders as tofu in most mono stacks
const FACES = ['(=^·ω·^=)', 'U^w^U', '(>w<)', '\\(°▽°)/', '(owo)', '(*^▽^*)', '(U·w·U)', '(^w^)', '(=·ω·=)']
const TRAIL_ROWS = 6
const LANES = [0.12, 0.56] // left offset within each gutter, as a fraction
const SLOTS = 2 // fallers per lane, half a cycle apart
const QUERY = '(min-width: 1200px) and (prefers-reduced-motion: no-preference)'

function useMedia(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const on = () => setMatch(mql.matches)
    mql.addEventListener('change', on)
    return () => mql.removeEventListener('change', on)
  }, [query])
  return match
}

// a kaomoji falling down with a vertical, nyan-style flag trail above it
function Faller({ seed, dur, delay, colors }: { seed: number; dur: number; delay: number; colors: string[] }) {
  const [n, setN] = useState(seed * 5)
  return (
    <div
      className="faller"
      style={{ animationDuration: `${dur}s`, animationDelay: `${delay}s` }}
      onAnimationIteration={e => { if (e.target === e.currentTarget) setN(n => n + 1) }}
    >
      {Array.from({ length: TRAIL_ROWS }, (_, r) => (
        <div key={r} className="trail-row" style={{ opacity: (r + 1) / TRAIL_ROWS }}>
          {colors.map((c, i) => <span key={i} style={{ color: c }}>█</span>)}
        </div>
      ))}
      <div className="face">{FACES[n % FACES.length]}</div>
    </div>
  )
}

export function KaomojiRain({ theme }: { theme: string }) {
  const show = useMedia(QUERY)
  if (!show) return null
  const colors = FLAG_COLORS[theme] ?? FLAG_COLORS.trans
  return (
    <div className="rain" aria-hidden="true">
      {['left', 'right'].map((side, s) => (
        <div key={side} className={`gutter ${side}`}>
          {LANES.map((x, l) => {
            // fallers sharing a lane share a speed and sit evenly apart, so they never overlap
            const lane = s * LANES.length + l
            const dur = 14 + (lane * 7) % 9
            const phase = (lane * 0.37) % 1
            return (
              <div key={l} className="lane" style={{ left: `${x * 100}%` }}>
                {Array.from({ length: SLOTS }, (_, k) => (
                  <Faller key={k} seed={lane * SLOTS + k} dur={dur} delay={-dur * (phase + k / SLOTS)} colors={colors} />
                ))}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
