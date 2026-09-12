import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { log, traced } from './log'
import type { WaveSignal, Waveform as Wave } from './types'

/**
 * Waveform viewer, in the shape engineers know from Verdi / SimVision:
 * a fixed signal-name column, a scrolling time canvas, a draggable cursor with
 * a per-signal value readout, and hex bus values drawn inside the bus shape.
 *
 * Canvas rather than SVG: a regression window is tens of thousands of edges and
 * one DOM node per edge does not survive a zoom drag.
 */

const ROW_H = 24
const RULER_H = 26
const PAD = 4
// The name and value gutters scale with the pane so a narrow window spends its
// pixels on the waveform itself, while a wide one stops widening the gutters.
const nameWidth = (w: number) => Math.round(Math.min(210, Math.max(112, w * 0.20)))
const valueWidth = (w: number) => Math.round(Math.min(110, Math.max(64, w * 0.10)))

function hex(bits: string): string {
  if (/[xz]/.test(bits)) return bits.includes('x') ? 'x' : 'z'
  if (!/^[01]+$/.test(bits)) return bits
  let out = ''
  // pad to a nibble boundary so the leading digit is not mis-weighted
  const padded = bits.padStart(Math.ceil(bits.length / 4) * 4, '0')
  for (let i = 0; i < padded.length; i += 4) out += parseInt(padded.slice(i, i + 4), 2).toString(16)
  return out.replace(/^0+(?=.)/, '')
}

/** Value of `sig` at time `t` — the last transition at or before t. */
function valueAt(sig: WaveSignal, t: number): string {
  const tr = sig.transitions
  let lo = 0, hi = tr.length - 1, best = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (tr[mid][0] <= t) { best = mid; lo = mid + 1 } else { hi = mid - 1 }
  }
  return best < 0 ? '-' : tr[best][1]
}

function css(el: HTMLElement, name: string, fallback: string): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

export function WaveformPane({ onSelect }: { onSelect?: (name: string) => void }) {
  const [wave, setWave] = useState<Wave | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [cursor, setCursor] = useState(0)
  const [view, setView] = useState({ start: 0, span: 300000 })
  const [selected, setSelected] = useState<string | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [wrapW, setWrapW] = useState(800)

  const signals = useMemo(() => wave?.signals ?? [], [wave])
  const params = wave?.parameters ?? []
  const unit = wave?.time_unit ?? 'ps'

  // ---- data ----
  const load = useCallback(async (end: number) => {
    setBusy('loading')
    const w = await traced(
      { stage: 'waveform', tool: 'vcd-reader', design: 'gamma',
        cmd: `read_vcd tb/dump.vcd -end ${end}` },
      () => api.waveform({ start: 0, end, maxTransitions: 40000 }),
      (v) => {
        if (!v.available) { log.error('WAVE', `no dump: ${v.error ?? 'unknown'}`); return { status: 'fail' } }
        log.info('WAVE', `${v.signals?.length ?? 0} signals, ${v.transition_count} transitions, 0-${v.end}${v.time_unit}`)
        if (v.parameters?.length) log.note('WAVE', `${v.parameters.length} elaboration parameters listed (not plotted)`)
        if (v.truncated) log.warn('WAVE', `transition budget reached at ${v.end}${v.time_unit} — window truncated`)
        return { status: v.available ? 'pass' : 'fail' }
      },
    )
    setBusy(null)
    if (w?.available) {
      setWave(w)
      setView({ start: 0, span: w.end || end })
    } else if (w) {
      setWave(w)
    }
  }, [])

  useEffect(() => { load(300000) }, [load])

  async function regenerate() {
    setBusy('regenerating')
    await traced(
      { stage: 'simulate', tool: 'verilator+cocotb', design: 'gamma',
        cmd: 'make -C tb WAVES=1 BP_PROFILE=single' },
      () => api.waveRun(true),
      (v) => {
        if (v.error) log.error('SIM', v.error)
        else log.info('SIM', `dump.vcd ${((v.size_bytes ?? 0) / 1048576).toFixed(1)} MB written`)
        return { status: v.ok === false ? 'fail' : 'pass' }
      },
    )
    setBusy(null)
    await load(300000)
  }

  // ---- sizing ----
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWrapW(e.contentRect.width))
    ro.observe(el)
    setWrapW(el.clientWidth)
    return () => ro.disconnect()
  }, [])

  const NAME_W = nameWidth(wrapW)
  const VALUE_W = valueWidth(wrapW)
  const plotW = Math.max(120, wrapW - NAME_W - VALUE_W)
  const tToX = useCallback((t: number) => ((t - view.start) / view.span) * plotW, [view, plotW])
  const xToT = useCallback((x: number) => view.start + (x / plotW) * view.span, [view, plotW])

  // ---- drawing ----
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || signals.length === 0) return
    const dpr = window.devicePixelRatio || 1
    const h = RULER_H + signals.length * ROW_H
    cv.width = plotW * dpr
    cv.height = h * dpr
    cv.style.width = `${plotW}px`
    cv.style.height = `${h}px`
    const g = cv.getContext('2d')
    if (!g) return
    g.setTransform(dpr, 0, 0, dpr, 0, 0)

    const root = cv
    const cBg = css(root, '--wave-bg', '#0d1219')
    const cGrid = css(root, '--wave-grid', '#1d2735')
    const cHi = css(root, '--wave-hi', '#4ade80')
    const cBus = css(root, '--wave-bus', '#60a5fa')
    const cX = css(root, '--wave-x', '#f87171')
    const cMuted = css(root, '--muted', '#8b9bb4')
    const cSel = css(root, '--accent', '#5b9dff')

    g.fillStyle = cBg
    g.fillRect(0, 0, plotW, h)

    // --- time ruler: pick a 1/2/5 x 10^n step so labels never collide ---
    const targetTicks = Math.max(2, Math.floor(plotW / 90))
    const raw = view.span / targetTicks
    const mag = Math.pow(10, Math.floor(Math.log10(raw)))
    const norm = raw / mag
    const step = (norm > 5 ? 10 : norm > 2 ? 5 : norm > 1 ? 2 : 1) * mag
    g.font = '10px ui-monospace, Menlo, monospace'
    g.textBaseline = 'middle'
    const first = Math.ceil(view.start / step) * step
    for (let t = first; t <= view.start + view.span; t += step) {
      const x = Math.round(tToX(t)) + 0.5
      g.strokeStyle = cGrid
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke()
      g.fillStyle = cMuted
      g.fillText(`${t}`, x + 3, RULER_H / 2)
    }
    g.strokeStyle = cGrid
    g.beginPath(); g.moveTo(0, RULER_H + 0.5); g.lineTo(plotW, RULER_H + 0.5); g.stroke()

    // --- signals ---
    signals.forEach((sig, i) => {
      const top = RULER_H + i * ROW_H
      const yHi = top + PAD
      const yLo = top + ROW_H - PAD
      const yMid = (yHi + yLo) / 2
      if (sig.name === selected) {
        g.fillStyle = 'rgba(91,157,255,0.08)'
        g.fillRect(0, top, plotW, ROW_H)
      }
      g.lineWidth = 1.4

      const tr = sig.transitions
      if (tr.length === 0) return
      // index of the last transition at or before the view start
      let i0 = 0
      while (i0 + 1 < tr.length && tr[i0 + 1][0] <= view.start) i0++

      if (sig.width === 1) {
        g.strokeStyle = cHi
        g.beginPath()
        let prevY = tr[i0][1] === '1' ? yHi : tr[i0][1] === '0' ? yLo : yMid
        let x = Math.max(0, tToX(tr[i0][0]))
        g.moveTo(x, prevY)
        for (let k = i0 + 1; k < tr.length; k++) {
          const [t, v] = tr[k]
          if (t > view.start + view.span) break
          const nx = tToX(t)
          g.lineTo(nx, prevY)
          const ny = v === '1' ? yHi : v === '0' ? yLo : yMid
          if (v === 'x' || v === 'z') { g.stroke(); g.strokeStyle = cX; g.beginPath(); g.moveTo(nx, prevY) }
          else if (g.strokeStyle === cX) { g.stroke(); g.strokeStyle = cHi; g.beginPath(); g.moveTo(nx, prevY) }
          g.lineTo(nx, ny)
          prevY = ny
          x = nx
        }
        g.lineTo(plotW, prevY)
        g.stroke()
      } else {
        // bus: hexagon segments, value centred when it fits
        g.font = '10px ui-monospace, Menlo, monospace'
        for (let k = i0; k < tr.length; k++) {
          const [t, v] = tr[k]
          if (t > view.start + view.span) break
          const x0 = Math.max(0, tToX(t))
          const next = k + 1 < tr.length ? tr[k + 1][0] : view.start + view.span
          const x1 = Math.min(plotW, tToX(next))
          if (x1 <= 0 || x1 - x0 < 0.4) continue
          const bad = /[xz]/.test(v)
          g.strokeStyle = bad ? cX : cBus
          const k2 = Math.min(3, (x1 - x0) / 2)
          g.beginPath()
          g.moveTo(x0, yMid); g.lineTo(x0 + k2, yHi); g.lineTo(x1 - k2, yHi)
          g.lineTo(x1, yMid); g.lineTo(x1 - k2, yLo); g.lineTo(x0 + k2, yLo)
          g.closePath(); g.stroke()
          const label = hex(v)
          if (x1 - x0 > label.length * 6 + 10) {
            g.fillStyle = bad ? cX : cBus
            g.fillText(label, (x0 + x1) / 2 - label.length * 3, yMid)
          }
        }
      }
    })

    // --- cursor ---
    const cx = Math.round(tToX(cursor)) + 0.5
    if (cx >= 0 && cx <= plotW) {
      g.strokeStyle = cSel
      g.setLineDash([3, 3])
      g.beginPath(); g.moveTo(cx, 0); g.lineTo(cx, h); g.stroke()
      g.setLineDash([])
    }
  }, [signals, view, plotW, cursor, selected])

  // ---- interaction ----
  function onCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    setCursor(Math.round(xToT(e.clientX - r.left)))
  }

  function onWheel(e: React.WheelEvent<HTMLCanvasElement>) {
    if (!e.ctrlKey && !e.metaKey && !e.shiftKey) return
    e.preventDefault()
    const r = e.currentTarget.getBoundingClientRect()
    const anchor = xToT(e.clientX - r.left)
    const factor = e.deltaY > 0 ? 1.25 : 0.8
    const span = Math.max(200, Math.min((wave?.end || 1e6) * 2, view.span * factor))
    // keep the time under the pointer fixed while the span changes
    setView({ start: Math.max(0, anchor - (anchor - view.start) * (span / view.span)), span })
  }

  function zoom(factor: number) {
    const mid = view.start + view.span / 2
    const span = Math.max(200, Math.min((wave?.end || 1e6) * 2, view.span * factor))
    setView({ start: Math.max(0, mid - span / 2), span })
  }

  function fit() { setView({ start: 0, span: wave?.end || 300000 }) }

  if (wave && !wave.available) {
    return (
      <div className="pane-empty">
        <p>No waveform dump yet.</p>
        <p className="muted small">
          The regression only traces when built with <code>WAVES=1</code> (~30% slower).
        </p>
        <button onClick={regenerate} disabled={!!busy}>
          {busy ? 'Running traced regression…' : 'Run traced regression'}
        </button>
      </div>
    )
  }

  return (
    <div className="wave">
      <div className="pane-toolbar">
        <div className="tb-group">
          <button className="tb-btn" onClick={() => zoom(0.5)} title="Zoom in">⊕</button>
          <button className="tb-btn" onClick={() => zoom(2)} title="Zoom out">⊖</button>
          <button className="tb-btn" onClick={fit} title="Zoom fit">⤢ Fit</button>
        </div>
        <div className="tb-group">
          <span className="tb-label">cursor</span>
          <span className="tb-readout">{cursor.toLocaleString()} {unit}</span>
          <span className="tb-label">window</span>
          <span className="tb-readout">
            {view.start.toLocaleString()} – {Math.round(view.start + view.span).toLocaleString()} {unit}
          </span>
        </div>
        <div className="tb-group tb-right">
          {wave?.truncated && <span className="pill pill-warn">truncated</span>}
          <button className="tb-btn" onClick={regenerate} disabled={!!busy}>
            {busy === 'regenerating' ? 'Re-simulating…' : '↻ Re-simulate'}
          </button>
        </div>
      </div>

      <div className="wave-body" ref={wrapRef}>
        <div className="wave-names" style={{ width: NAME_W }}>
          <div className="wave-names-head" style={{ height: RULER_H }}>signal</div>
          {signals.map((s) => (
            <button
              key={s.name}
              className={`wave-name ${selected === s.name ? 'wave-name-sel' : ''}`}
              style={{ height: ROW_H }}
              onClick={() => { setSelected(s.name); onSelect?.(s.name) }}
              title={`${s.scope}.${s.name} [${s.width}]`}
            >
              <span className="wave-name-txt">{s.name}</span>
              {s.width > 1 && <span className="wave-name-w">[{s.width - 1}:0]</span>}
            </button>
          ))}
        </div>

        <canvas
          ref={canvasRef}
          className="wave-canvas"
          onClick={onCanvasClick}
          onWheel={onWheel}
          title="click to place cursor · ⌘/Ctrl+wheel to zoom"
        />

        <div className="wave-values" style={{ width: VALUE_W }}>
          <div className="wave-names-head" style={{ height: RULER_H }}>value</div>
          {signals.map((s) => {
            const v = valueAt(s, cursor)
            const bad = /[xz]/.test(v)
            return (
              <div key={s.name} className={`wave-val ${bad ? 'wave-val-x' : ''}`} style={{ height: ROW_H }}>
                {s.width === 1 ? v : hex(v)}
              </div>
            )
          })}
        </div>
      </div>

      {params.length > 0 && (
        <div className="wave-params">
          <span className="tb-label">parameters</span>
          {params.map((p) => (
            <span key={p.name} className="wave-param" title={`${p.name}[${p.width - 1}:0] = ${p.value}`}>
              <b>{p.name}</b>
              <span>{p.width > 1 ? hex(p.value) : p.value}</span>
            </span>
          ))}
        </div>
      )}

      <div className="pane-foot muted small">
        {signals.length} signals · scope <code>{wave?.scope}</code> · {wave?.transition_count?.toLocaleString()} transitions ·
        click to place cursor, ⌘/Ctrl+wheel to zoom
      </div>
    </div>
  )
}
