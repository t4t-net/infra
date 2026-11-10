import { render } from 'preact'
import './index.css'
import { App, setData } from './app.tsx'

const root = document.getElementById('app')!
fetch('data.json', { cache: 'no-store' })
  .then(r => { if (!r.ok) throw new Error(`data.json: ${r.status}`); return r.json() })
  .then(d => { setData(d); render(<App />, root) })
  .catch(e => { root.textContent = `couldn't load prices (${e.message}). the next hourly scrape regenerates them.` })
