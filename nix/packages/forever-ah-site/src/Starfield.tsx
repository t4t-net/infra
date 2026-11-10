import type { RefObject } from 'preact'
import { useEffect, useRef } from 'preact/hooks'
import { FLAG_COLORS } from './TransFlag'

// everything is snapped to a character grid so it reads as ascii, not particles
// three parallax layers: far stars are small, dim and slow, near ones big, bright and fast
const LAYERS = [
  { weight: 0.6, glyphs: ['.', '.', '·'], speed: 1.5, alpha: 0.22, tail: 0 },
  { weight: 0.3, glyphs: ['·', '+'], speed: 3.5, alpha: 0.4, tail: 1 },
  { weight: 0.1, glyphs: ['*', '+', '✦'], speed: 7, alpha: 0.7, tail: 3 },
] // speed is rows per second
const FALL_TAIL = ['·', '.', '.']
const STAR_DENSITY = 1 / 40 // stars per grid cell
const MOTION = '(prefers-reduced-motion: no-preference)'

type Layer = typeof LAYERS[number]
type Star = { x: number; y: number; layer: Layer; glyph: string; phase: number; speed: number; tint: number }

function pickLayer() {
  let r = Math.random()
  for (const l of LAYERS) if ((r -= l.weight) < 0) return l
  return LAYERS[0]
}

// open is the list of columns stars may fall in
function makeStar(open: number[], y: number): Star {
  const layer = pickLayer()
  return {
    x: open[Math.floor(Math.random() * open.length)],
    y,
    layer,
    glyph: layer.glyphs[Math.floor(Math.random() * layer.glyphs.length)],
    phase: Math.random() * Math.PI * 2,
    speed: 0.4 + Math.random() * 1.2,
    // near stars always carry a flag colour, the rest mostly stay plain
    tint: layer.tail > 1 || Math.random() < 0.2 ? Math.floor(Math.random() * 5) : -1,
  }
}

function makeStars(open: number[], rows: number): Star[] {
  return Array.from({ length: Math.round(open.length * rows * STAR_DENSITY) }, () => makeStar(open, Math.random() * rows))
}

export function Starfield({ theme, frameRef }: { theme: string; frameRef: RefObject<HTMLElement> }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const colorsRef = useRef(FLAG_COLORS[theme] ?? FLAG_COLORS.trans)
  colorsRef.current = FLAG_COLORS[theme] ?? FLAG_COLORS.trans
  // the static (reduced-motion) field still needs a repaint when the theme flips
  const redrawRef = useRef(() => {})
  useEffect(() => redrawRef.current(), [theme])

  useEffect(() => {
    const canvas = ref.current!
    const ctx = canvas.getContext('2d')!
    const css = getComputedStyle(document.documentElement)
    const fontSize = parseFloat(css.fontSize)
    const font = `${fontSize}px ${css.fontFamily}`
    const text = css.color
    let cw = 9, ch = 18, rows = 0
    let open: number[] = []
    let stars: Star[] = []

    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      canvas.width = innerWidth * dpr
      canvas.height = innerHeight * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.font = font
      ctx.textBaseline = 'top'
      cw = ctx.measureText('0').width
      ch = Math.round(fontSize * 1.2)
      const cols = Math.ceil(innerWidth / cw)
      rows = Math.ceil(innerHeight / ch)
      // keep a one-cell moat around the sparkle border so stars never crowd it;
      // phone gutters are thinner than a cell, so there they vanish entirely
      const frame = frameRef.current?.getBoundingClientRect()
      open = Array.from({ length: cols }, (_, c) => c)
        .filter(c => !frame || (c + 1) * cw <= frame.left - cw || c * cw >= frame.right + cw)
      stars = makeStars(open, rows)
    }

    const glyph = (g: string, x: number, y: number, color: string, alpha: number) => {
      ctx.globalAlpha = alpha
      ctx.fillStyle = color
      ctx.fillText(g, x * cw, y * ch)
    }

    const draw = (now: number) => {
      const colors = colorsRef.current
      ctx.clearRect(0, 0, innerWidth, innerHeight)
      for (const s of stars) {
        const tw = 0.6 + 0.4 * Math.sin(now / 1000 * s.speed + s.phase)
        const y = Math.floor(s.y)
        const color = s.tint < 0 ? text : colors[s.tint]
        glyph(s.glyph, s.x, y, color, s.layer.alpha * tw)
        // short tail above the faster stars, stepping through the next flag stripes
        for (let i = 1; i <= s.layer.tail; i++)
          glyph(FALL_TAIL[i - 1], s.x, y - i, colors[(Math.max(s.tint, 0) + i) % colors.length], s.layer.alpha * (1 - i / (s.layer.tail + 1)))
      }
      ctx.globalAlpha = 1
    }

    resize()
    redrawRef.current = () => draw(performance.now())
    const onResize = () => { resize(); draw(performance.now()) }
    addEventListener('resize', onResize)

    const mql = window.matchMedia(MOTION)
    if (!mql.matches) {
      draw(0)
      return () => removeEventListener('resize', onResize)
    }

    let raf = 0, last = performance.now()
    const frame = (now: number) => {
      // clamp so a backgrounded tab doesn't jump everything on return
      const dt = Math.min(now - last, 250)
      last = now
      for (let i = 0; i < stars.length; i++) {
        const s = stars[i]
        s.y += s.layer.speed * dt / 1000
        // once the tail clears the bottom, respawn above the top in a fresh column
        if (s.y - s.layer.tail > rows) stars[i] = makeStar(open, -1)
      }
      draw(now)
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', onResize) }
  }, [])

  return <canvas ref={ref} className="starfield" aria-hidden="true" />
}
