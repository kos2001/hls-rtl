import { useEffect, useState } from 'react'

/** Elapsed-seconds ticker while `busy` is true. */
export function useElapsed(busy: boolean): number {
  const [sec, setSec] = useState(0)
  useEffect(() => {
    if (!busy) { setSec(0); return }
    const t0 = Date.now()
    const id = setInterval(() => setSec(Math.floor((Date.now() - t0) / 1000)), 1000)
    return () => clearInterval(id)
  }, [busy])
  return sec
}

export function Busy({ label, sec, hint }: { label: string; sec: number; hint?: string }) {
  return (
    <div className="busy-row">
      <span className="spinner" />
      <span className="muted small">
        {label} — {sec}s{hint ? ` (${hint})` : ''}
      </span>
    </div>
  )
}

/** Tiny inline SVG sparkline (no deps). */
export function Sparkline({ values, width = 120, height = 28 }:
  { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = width / (values.length - 1)
  const pts = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(1)}`)
    .join(' ')
  const last = values[values.length - 1]
  const lx = ((values.length - 1) * step).toFixed(1)
  const ly = (height - 3 - ((last - min) / span) * (height - 6)).toFixed(1)
  return (
    <svg className="sparkline" width={width} height={height}
      viewBox={`0 0 ${width} ${height}`} aria-label={`trend ${values.join(', ')}`}>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx={lx} cy={ly} r="2.4" fill="currentColor" />
    </svg>
  )
}
