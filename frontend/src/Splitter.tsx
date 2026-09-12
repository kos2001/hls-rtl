import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Draggable pane divider, the way every EDA GUI lets you rebalance its docks.
 *
 * The size lives in a CSS custom property on the shell (`--nav-w`, `--props-w`,
 * `--console-h`) rather than in React state that each pane reads: the panes stay
 * dumb, and the *default* can be a `clamp()` expression that already tracks the
 * viewport. A drag overrides that default; double-click clears the override and
 * hands the pane back to the fluid default.
 */

export type Axis = 'x' | 'y'

interface Props {
  axis: Axis
  /** CSS custom property this splitter drives, e.g. '--nav-w'. */
  varName: string
  /** Which way the pane grows relative to the pointer. */
  invert?: boolean
  min: number
  max: number
  label: string
}

/** Persisted overrides, so a rebalanced workspace survives a reload. */
const KEY = 'wb-panes'

function readAll(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} }
}

function writeOne(varName: string, px: number | null) {
  const all = readAll()
  if (px == null) delete all[varName]
  else all[varName] = px
  try { localStorage.setItem(KEY, JSON.stringify(all)) } catch { /* private mode */ }
}

/** Apply saved overrides once, before first paint, to avoid a resize flash. */
export function applySavedPanes(el: HTMLElement | null) {
  if (!el) return
  for (const [k, v] of Object.entries(readAll())) el.style.setProperty(k, `${v}px`)
}

export function Splitter({ axis, varName, invert, min, max, label }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)

  const shell = useCallback(
    () => ref.current?.closest('.workbench') as HTMLElement | null, [])

  const apply = useCallback((px: number) => {
    const clamped = Math.min(max, Math.max(min, px))
    shell()?.style.setProperty(varName, `${clamped}px`)
    writeOne(varName, clamped)
  }, [max, min, shell, varName])

  useEffect(() => {
    if (!dragging) return
    function move(e: PointerEvent) {
      const el = ref.current
      if (!el) return
      // Measure against the neighbour the splitter actually resizes, so the
      // pane tracks the pointer exactly instead of drifting by its own width.
      const sib = (invert ? el.nextElementSibling : el.previousElementSibling) as HTMLElement | null
      if (!sib) return
      const r = sib.getBoundingClientRect()
      apply(axis === 'x'
        ? (invert ? r.right - e.clientX : e.clientX - r.left)
        : (invert ? r.bottom - e.clientY : e.clientY - r.top))
    }
    function up() { setDragging(false) }
    // Listen on the window: the pointer routinely leaves the 5px hit area.
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    const prev = document.body.style.cursor
    document.body.style.cursor = axis === 'x' ? 'col-resize' : 'row-resize'
    document.body.style.userSelect = 'none'
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      document.body.style.cursor = prev
      document.body.style.userSelect = ''
    }
  }, [dragging, axis, invert, apply])

  function reset() {
    shell()?.style.removeProperty(varName)
    writeOne(varName, null)
  }

  /** Keyboard resize, so the layout is reachable without a pointer. */
  function onKey(e: React.KeyboardEvent) {
    const el = ref.current
    const sib = (invert ? el?.nextElementSibling : el?.previousElementSibling) as HTMLElement | null
    if (!sib) return
    const cur = axis === 'x' ? sib.getBoundingClientRect().width : sib.getBoundingClientRect().height
    const back = axis === 'x' ? 'ArrowLeft' : 'ArrowUp'
    const fwd = axis === 'x' ? 'ArrowRight' : 'ArrowDown'
    if (e.key === back || e.key === fwd) {
      e.preventDefault()
      const d = (e.key === fwd ? 16 : -16) * (invert ? -1 : 1)
      apply(cur + d)
    } else if (e.key === 'Enter') {
      e.preventDefault(); reset()
    }
  }

  return (
    <div
      ref={ref}
      className={`splitter splitter-${axis} ${dragging ? 'splitter-active' : ''}`}
      role="separator"
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      aria-label={`${label} — drag to resize, double-click or Enter to reset`}
      tabIndex={0}
      onKeyDown={onKey}
      onPointerDown={(e) => { e.preventDefault(); setDragging(true) }}
      onDoubleClick={reset}
      title={`${label}: drag to resize · double-click to reset`}
    />
  )
}
