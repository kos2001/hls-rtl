import { useSyncExternalStore } from 'react'

/**
 * Transcript store — the tool log every commercial EDA flow keeps.
 *
 * Xcelium, Genus and VCS all funnel every action into one severity-tagged,
 * timestamped stream, and engineers debug from that stream rather than from the
 * GUI state. This mirrors it: every API call the workbench makes writes a
 * banner, its findings, and a verdict here, so the console is a complete record
 * of the session rather than decoration.
 *
 * Message shape follows skills/semiconductor-eda/eda-transcript-conventions:
 *   SEV-[TAG] object: message
 */

export type Severity = 'FATAL' | 'ERROR' | 'WARN' | 'NOTE' | 'INFO' | 'CMD'

export interface LogLine {
  id: number
  ts: number
  sev: Severity
  tag: string
  text: string
  /** Monospaced verbatim block (tool output) rendered under the line. */
  detail?: string
}

/** Severity ordering for the console's threshold filter. */
export const SEV_RANK: Record<Severity, number> = {
  FATAL: 0, ERROR: 1, WARN: 2, NOTE: 3, INFO: 4, CMD: 4,
}

const MAX_LINES = 2000

let lines: LogLine[] = []
let seq = 0
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

function push(sev: Severity, tag: string, text: string, detail?: string) {
  lines = [...lines, { id: ++seq, ts: Date.now(), sev, tag, text, detail }]
  if (lines.length > MAX_LINES) lines = lines.slice(-MAX_LINES)
  emit()
}

export const log = {
  fatal: (tag: string, text: string, detail?: string) => push('FATAL', tag, text, detail),
  error: (tag: string, text: string, detail?: string) => push('ERROR', tag, text, detail),
  warn: (tag: string, text: string, detail?: string) => push('WARN', tag, text, detail),
  note: (tag: string, text: string, detail?: string) => push('NOTE', tag, text, detail),
  info: (tag: string, text: string, detail?: string) => push('INFO', tag, text, detail),
  /** A command the user invoked — echoed like a tool shell echoes its input. */
  cmd: (text: string) => push('CMD', 'EXEC', text),

  /** Stage banner, as a tool prints when it enters a flow step. */
  banner: (stage: string, tool: string, design: string) =>
    push('INFO', 'STAGE', `▶ ${stage}  ·  tool: ${tool}  ·  design: ${design}`),

  /** Closing line for a stage: verdict plus elapsed, the way a tool reports. */
  verdict: (stage: string, status: string, ms: number, extra = '') => {
    const sev: Severity =
      status === 'pass' || status === 'PASS' || status === 'SIGNED_OFF' ? 'INFO'
        : status === 'skip' || status === 'CONDITIONAL' ? 'WARN' : 'ERROR'
    push(sev, 'STAGE',
      `◀ ${stage} : ${status.toUpperCase()}   elapsed ${(ms / 1000).toFixed(2)}s${extra ? `   ${extra}` : ''}`)
  },

  clear: () => { lines = []; emit() },
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

function snapshot() {
  return lines
}

export function useLog(): LogLine[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

/**
 * Run an async action with full transcript framing: echo, banner, verdict,
 * and an ERROR line carrying the failure text if it throws.
 *
 * Returns the value, or null on failure — callers render "no result" rather
 * than crashing the pane, because the console already carries the diagnosis.
 */
export async function traced<T>(
  opts: { stage: string; tool: string; design: string; cmd: string },
  fn: () => Promise<T>,
  summarize?: (v: T) => { status: string; extra?: string; lines?: () => void },
): Promise<T | null> {
  const t0 = performance.now()
  log.cmd(opts.cmd)
  log.banner(opts.stage, opts.tool, opts.design)
  try {
    const v = await fn()
    const s = summarize?.(v)
    s?.lines?.()
    log.verdict(opts.stage, s?.status ?? 'pass', performance.now() - t0, s?.extra)
    return v
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    log.error(opts.stage.toUpperCase().slice(0, 8), `${opts.design}: ${msg}`)
    log.verdict(opts.stage, 'fail', performance.now() - t0)
    return null
  }
}
