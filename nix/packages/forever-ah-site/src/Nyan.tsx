import { useState } from 'preact/hooks'
import { FLAG_COLORS } from './TransFlag'

const CHANCE = 1 / 10000 // per page load; ?nyan forces it
const SEGMENTS = 16 // trail chunks, alternate ones bob up/down like the original rainbow

// the original nyan cat sprite (www.nyan.cat/cats/original.gif), 34x21 art px drawn at 8x;
// the trail is plain divs on the same art-pixel grid so we can paint it in flag stripes
export function Nyan({ theme }: { theme: string }) {
  const [top] = useState(() => 15 + Math.random() * 55)
  const [show] = useState(() =>
    new URLSearchParams(location.search).has('nyan') ||
    (Math.random() < CHANCE && !window.matchMedia('(prefers-reduced-motion: reduce)').matches))
  if (!show) return null
  const colors = FLAG_COLORS[theme] ?? FLAG_COLORS.trans
  return (
    <div className="nyan" style={{ top: `${top}vh` }} aria-hidden="true">
      <div className="nyan-trail">
        {Array.from({ length: SEGMENTS }, (_, k) => (
          <div key={k} className="nyan-seg">
            {colors.map((c, i) => <div key={i} style={{ background: c }} />)}
          </div>
        ))}
      </div>
      <img className="nyan-cat" src="nyan.gif" alt="" />
    </div>
  )
}
