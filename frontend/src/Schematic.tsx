import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { log, traced } from './log'
import type { Schematic as Schem, SchematicEdge, SchematicNode } from './types'

/**
 * RTL schematic view — the netlist drawn left-to-right by layer, the way a
 * schematic browser (Verdi, Innovus netlist view) presents a module.
 *
 * SVG here rather than canvas: the netlist is ~80 nodes, and SVG gives hit
 * testing, hover highlight and text selection for free at that size.
 *
 * Backend cuts feedback through sequential cells, so layer order is meaningful:
 * layer 0 holds inputs and flop/memory outputs, the last layer holds outputs.
 */

const NODE_W = 104
const NODE_H = 34
const COL_GAP = 96
const ROW_GAP = 16
const MARGIN = 28

interface Placed extends SchematicNode {
  x: number
  y: number
}

function layout(nodes: SchematicNode[]): { placed: Placed[]; w: number; h: number } {
  const byLayer = new Map<number, SchematicNode[]>()
  for (const n of nodes) {
    const arr = byLayer.get(n.layer) ?? []
    arr.push(n)
    byLayer.set(n.layer, arr)
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b)
  const tallest = Math.max(...layers.map((l) => byLayer.get(l)!.length), 1)
  const h = tallest * (NODE_H + ROW_GAP) + MARGIN * 2
  const placed: Placed[] = []
  layers.forEach((l, li) => {
    // stable order inside a column: ports first, then by label, so redraws
    // don't shuffle the picture
    const col = byLayer.get(l)!.slice().sort((a, b) =>
      (a.kind === b.kind ? 0 : a.kind === 'port' ? -1 : 1) || a.label.localeCompare(b.label))
    const colH = col.length * (NODE_H + ROW_GAP)
    const y0 = (h - colH) / 2
    col.forEach((n, i) => {
      placed.push({ ...n, x: MARGIN + li * (NODE_W + COL_GAP), y: y0 + i * (NODE_H + ROW_GAP) })
    })
  })
  const w = MARGIN * 2 + layers.length * (NODE_W + COL_GAP)
  return { placed, w, h }
}

/** Orthogonal-ish connector: out the right, into the left, with a mid elbow. */
function path(a: Placed, b: Placed): string {
  const x0 = a.x + NODE_W
  const y0 = a.y + NODE_H / 2
  const x1 = b.x
  const y1 = b.y + NODE_H / 2
  if (x1 <= x0 + 8) {
    // feedback / same-column: route below the row so it stays readable
    const dip = Math.max(y0, y1) + NODE_H
    return `M${x0},${y0} L${x0 + 12},${y0} L${x0 + 12},${dip} L${x1 - 12},${dip} L${x1 - 12},${y1} L${x1},${y1}`
  }
  const mx = (x0 + x1) / 2
  return `M${x0},${y0} L${mx},${y0} L${mx},${y1} L${x1},${y1}`
}

export function SchematicPane({ onSelect }: { onSelect?: (n: SchematicNode) => void }) {
  const [g, setG] = useState<Schem | null>(null)
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)

  useEffect(() => { void load() }, [])

  async function load() {
    setBusy(true)
    const r = await traced(
      { stage: 'elaborate', tool: 'yosys', design: 'gamma',
        cmd: "yosys -p 'read_verilog rtl/gamma.v; hierarchy -top gamma; proc; opt_clean; write_json'" },
      () => api.schematic(),
      (v) => {
        if (!v.available) { log.error('SCHEM', v.error ?? 'yosys unavailable'); return { status: 'fail' } }
        log.info('SCHEM', `${v.node_count} nodes, ${v.edge_count} nets, ${v.layers} levels`)
        for (const [t, n] of Object.entries(v.stats ?? {})) log.note('SCHEM', `${t} x${n}`)
        if (v.truncated) log.warn('SCHEM', 'node budget reached — graph truncated')
        return { status: 'pass' }
      },
    )
    if (r) setG(r)
    setBusy(false)
  }

  const { placed, w, h } = useMemo(
    () => (g?.nodes ? layout(g.nodes) : { placed: [], w: 0, h: 0 }), [g],
  )
  const byId = useMemo(() => new Map(placed.map((n) => [n.id, n])), [placed])

  const active = hover ?? sel
  const litEdges = useMemo(() => {
    if (!active) return new Set<number>()
    const s = new Set<number>()
    ;(g?.edges ?? []).forEach((e, i) => { if (e.from === active || e.to === active) s.add(i) })
    return s
  }, [active, g])

  if (g && !g.available) {
    return <div className="pane-empty"><p>Schematic unavailable.</p><p className="muted small">{g.error}</p></div>
  }

  function pick(n: SchematicNode) {
    setSel(n.id)
    onSelect?.(n)
    log.info('SCHEM', `selected ${n.kind} ${n.name ?? n.label}` +
      (n.src_line ? ` (rtl/gamma.v:${n.src_line})` : ''))
  }

  return (
    <div className="schem">
      <div className="pane-toolbar">
        <div className="tb-group">
          <button className="tb-btn" onClick={() => setZoom((z) => Math.min(3, z * 1.25))}>⊕</button>
          <button className="tb-btn" onClick={() => setZoom((z) => Math.max(0.25, z / 1.25))}>⊖</button>
          <button className="tb-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}>⤢ Fit</button>
        </div>
        <div className="tb-group">
          <span className="tb-label">cells</span><span className="tb-readout">{g?.node_count ?? '—'}</span>
          <span className="tb-label">nets</span><span className="tb-readout">{g?.edge_count ?? '—'}</span>
          <span className="tb-label">levels</span><span className="tb-readout">{g?.layers ?? '—'}</span>
        </div>
        <div className="tb-group tb-right">
          <Legend />
          <button className="tb-btn" onClick={load} disabled={busy}>{busy ? 'Elaborating…' : '↻ Re-elaborate'}</button>
        </div>
      </div>

      <div
        className="schem-canvas"
        onMouseDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y } }}
        onMouseMove={(e) => {
          if (!drag.current) return
          setPan({ x: drag.current.px + (e.clientX - drag.current.x),
                   y: drag.current.py + (e.clientY - drag.current.y) })
        }}
        onMouseUp={() => { drag.current = null }}
        onMouseLeave={() => { drag.current = null }}
      >
        {/* viewBox carries the graph's natural extent, so the drawing fits the
            pane at any window size; pan/zoom then compose on top of that. */}
        <svg width="100%" height="100%" role="img" aria-label="RTL schematic"
             viewBox={w && h ? `0 0 ${w} ${h}` : undefined}
             preserveAspectRatio="xMidYMid meet">
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {(g?.edges ?? []).map((e: SchematicEdge, i) => {
              const a = byId.get(e.from), b = byId.get(e.to)
              if (!a || !b) return null
              const lit = litEdges.has(i)
              return (
                <g key={i} className={`sch-edge ${lit ? 'sch-edge-lit' : ''}`}>
                  <path d={path(a, b)} fill="none"
                        strokeWidth={e.width > 1 ? 2 : 1.1} />
                  {lit && (
                    <text x={(a.x + NODE_W + b.x) / 2} y={(a.y + b.y) / 2 + NODE_H / 2 - 5}
                          className="sch-netlabel" textAnchor="middle">
                      {e.net}{e.width > 1 ? `[${e.width - 1}:0]` : ''}
                    </text>
                  )}
                </g>
              )
            })}
            {placed.map((n) => (
              <g key={n.id}
                 className={`sch-node sch-${n.cls} ${sel === n.id ? 'sch-sel' : ''}`}
                 transform={`translate(${n.x},${n.y})`}
                 onMouseEnter={() => setHover(n.id)}
                 onMouseLeave={() => setHover(null)}
                 onClick={(e) => { e.stopPropagation(); pick(n) }}>
                <rect width={NODE_W} height={NODE_H} rx={n.kind === 'port' ? 16 : 4} />
                <text className="sch-label" x={NODE_W / 2} y={n.name && n.name !== n.label ? 14 : 20}
                      textAnchor="middle">{n.label}</text>
                {n.name && n.name !== n.label && (
                  <text className="sch-sub" x={NODE_W / 2} y={26} textAnchor="middle">{n.name}</text>
                )}
                {n.width > 1 && (
                  <text className="sch-w" x={NODE_W - 5} y={NODE_H - 4} textAnchor="end">{n.width}b</text>
                )}
              </g>
            ))}
          </g>
        </svg>
      </div>

      <div className="pane-foot muted small">
        {g?.note} · drag to pan, ⊕/⊖ to zoom, click a cell to cross-probe its source line
      </div>
    </div>
  )
}

const LEGEND: [string, string][] = [
  ['in', 'input'], ['out', 'output'], ['seq', 'flop'],
  ['mem', 'memory'], ['mux', 'mux'], ['arith', 'arith'], ['logic', 'logic'],
]

function Legend() {
  return (
    <span className="sch-legend">
      {LEGEND.map(([cls, label]) => (
        <span key={cls} className="sch-legend-item">
          <i className={`sch-swatch sch-sw-${cls}`} />{label}
        </span>
      ))}
    </span>
  )
}
