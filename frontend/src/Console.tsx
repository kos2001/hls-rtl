import { useEffect, useMemo, useRef, useState } from 'react'
import { SEV_RANK, log, useLog } from './log'
import type { Severity } from './log'
import { useT } from './i18n'
import { Icon } from './components/Icon'

/**
 * Tool transcript — the bottom pane every commercial EDA GUI keeps.
 *
 * Filtering is by *threshold*, not by checkbox set: engineers think "show me
 * warnings and worse", and a threshold makes that one click instead of three.
 * A free-text filter on top of it covers "show me just the LATCH findings".
 */

const LEVELS: { key: Severity; label: string }[] = [
  { key: 'FATAL', label: 'F' },
  { key: 'ERROR', label: 'E' },
  { key: 'WARN', label: 'W' },
  { key: 'NOTE', label: 'N' },
  { key: 'INFO', label: 'I' },
]

function ts(t: number): string {
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

export function Console({ open, onToggle, onExport }: { open: boolean; onToggle: () => void; onExport?: () => void }) {
  const t = useT()
  const lines = useLog()
  const [threshold, setThreshold] = useState<Severity>('INFO')
  const [q, setQ] = useState('')
  const [follow, setFollow] = useState(true)
  const bodyRef = useRef<HTMLDivElement>(null)

  const counts = useMemo(() => {
    const c: Record<string, number> = { FATAL: 0, ERROR: 0, WARN: 0, NOTE: 0, INFO: 0 }
    for (const l of lines) if (l.sev in c) c[l.sev]++
    return c
  }, [lines])

  const shown = useMemo(() => {
    const max = SEV_RANK[threshold]
    const needle = q.trim().toLowerCase()
    return lines.filter((l) =>
      SEV_RANK[l.sev] <= max &&
      (!needle || l.text.toLowerCase().includes(needle) || l.tag.toLowerCase().includes(needle)))
  }, [lines, threshold, q])

  useEffect(() => {
    // Set scrollTop directly rather than scrollIntoView: the latter scrolls
    // every scrollable ancestor, so following the transcript was silently
    // scrolling the work area too — the Overview's opening claim was pushed off
    // the top of the pane on load.
    if (open && follow && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [shown, open, follow])

  function copyAll() {
    const text = shown.map((l) =>
      `${ts(l.ts)} ${l.sev}-[${l.tag}] ${l.text}${l.detail ? `\n${l.detail}` : ''}`).join('\n')
    if (!navigator.clipboard) { log.warn('CONSOLE', 'Clipboard unavailable; use Export instead.'); return }
    void navigator.clipboard.writeText(text).then(() => log.info('CONSOLE', `${shown.length} line(s) copied to clipboard`))
      .catch(() => log.warn('CONSOLE', 'Clipboard access denied; use Export instead.'))
  }

  return (
    <section className={`console ${open ? '' : 'console-collapsed'}`}>
      <header className="console-head">
        <button className="console-toggle" onClick={onToggle} title={open ? 'Collapse' : 'Expand'} aria-expanded={open} aria-controls="session-transcript">
          <Icon name="terminal" size={16} /> {t('Transcript')} <Icon name="down" size={13} style={{ transform: open ? undefined : 'rotate(180deg)' }} />
        </button>

        <div className="sev-filter" role="group" aria-label="severity threshold">
          {LEVELS.map((l) => (
            <button
              key={l.key}
              className={`sev-btn sev-${l.key} ${SEV_RANK[threshold] >= SEV_RANK[l.key] ? 'sev-on' : ''}`}
              onClick={() => setThreshold(l.key)}
              title={`Show ${l.key} and more severe`}
            >
              {l.label}
              <span className="sev-count">{counts[l.key] ?? 0}</span>
            </button>
          ))}
        </div>

        <input className="console-search" value={q} onChange={(e) => setQ(e.target.value)}
               placeholder={t('filter (tag or text)')} aria-label={t('Filter transcript')} />

        <div className="console-actions">
          <label className="console-follow">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            {t('follow')}
          </label>
          <button className="tb-btn" onClick={copyAll}>{t('Copy')}</button>
          <button className="tb-btn" onClick={log.clear}>{t('Clear')}</button>
          {onExport && <button className="tb-btn transcript-export" onClick={onExport} title={t('Export transcript…')} aria-label={t('Export transcript…')}><Icon name="download" size={14} /></button>}
        </div>
      </header>

      {open && (
        <div className="console-body" id="session-transcript" ref={bodyRef}>
          {shown.length === 0 && (
            <div className="console-line console-empty">
              <span className="muted small">
                {t('No messages at this threshold. Run a flow from the toolbar.')}
              </span>
            </div>
          )}
          {shown.map((l) => (
            <div key={l.id} className={`console-line cl-${l.sev}`}>
              <span className="cl-ts">{ts(l.ts)}</span>
              <span className={`cl-sev cl-sev-${l.sev}`}>
                {l.sev === 'CMD' ? '>' : `${l.sev}-[${l.tag}]`}
              </span>
              <span className="cl-text">{l.text}</span>
              {l.detail && <pre className="cl-detail">{l.detail}</pre>}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
