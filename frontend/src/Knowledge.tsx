import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { log, traced } from './log'
import type { KbChunk, KbStats } from './types'
import { useT } from './i18n'

/**
 * Knowledge-base browser — what the agent is actually given as grounding.
 *
 * The point is inspectability. An agent answer is only as good as the passages
 * behind it, so the same retrieval the gateway request uses is exposed here with
 * its scores: if an answer was wrong, you can see whether retrieval missed or
 * the model did, which are very different bugs.
 */

const SAMPLES = [
  'in_ready 계산식과 조합 경로',
  'backpressure profile 종류',
  'SystemC 미러는 골든과 어떻게 비교되나',
  'FIFO 포인터와 점유 카운트 갱신',
  'mutation check',
]

const KIND_LABEL: Record<string, string> = {
  verilog: 'RTL', python: 'PY', cpp: 'C++', markdown: 'DOC', live: 'LIVE',
}

function Hit({ c, rank }: { c: KbChunk; rank: number }) {
  const [open, setOpen] = useState(rank === 0)
  return (
    <div className={`kb-hit ${open ? 'kb-hit-open' : ''}`}>
      <button className="kb-hit-head" onClick={() => setOpen(!open)}>
        <span className="kb-rank">{rank + 1}</span>
        <span className={`kb-kind kb-kind-${c.kind}`}>{KIND_LABEL[c.kind] ?? c.kind}</span>
        <span className="kb-cite">{c.citation}</span>
        <span className="kb-title">{c.title}</span>
        <span className="kb-score">{c.score?.toFixed(1) ?? '—'}</span>
        <span className="step-chevron">{open ? '▾' : '▸'}</span>
      </button>
      {open && c.text && <pre className="kb-text">{c.text}</pre>}
    </div>
  )
}

export function KnowledgePane() {
  const t = useT()
  const [stats, setStats] = useState<KbStats | null>(null)
  const [q, setQ] = useState(SAMPLES[0])
  const [hits, setHits] = useState<KbChunk[] | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.kbStats().then(setStats).catch(() => setStats(null)) }, [])

  async function run(query = q) {
    if (!query.trim()) return
    setBusy(true)
    const r = await traced(
      { stage: 'retrieve', tool: 'bm25-lexical', design: 'gamma',
        cmd: `kb search "${query.slice(0, 50)}"` },
      () => api.kbSearch(query),
      (v) => {
        if (!v.count) log.warn('KB', `no passage matched "${query}" — the agent would answer unglounded`)
        else log.info('KB', `${v.count} passages, top ${v.results[0].citation} (${v.results[0].score?.toFixed(1)})`)
        return { status: v.count ? 'pass' : 'skip', extra: `${v.count} hits` }
      })
    if (r) setHits(r.results)
    setBusy(false)
  }

  const sourceRows = useMemo(
    () => Object.entries(stats?.sources ?? {}).sort((a, b) => b[1] - a[1]), [stats])

  return (
    <div className="view-scroll">
      <div className="panel">
        <div className="panel-head">
          <h2>{t('Knowledge Base')}</h2>
          <span className="muted small">
            {stats ? `${stats.chunks} passages · ${stats.terms} terms · ${stats.retrieval}` : 'loading…'}
          </span>
        </div>
        <p className="muted small">
          Grounding for <code>/chat</code> and <code>/plan</code>: pinned passages (module
          contract, live results) plus whatever the question retrieves. Lexical, not
          embeddings — the queries are full of identifiers like <code>in_ready</code> and{' '}
          <code>FIFO_DEPTH</code>, and vector similarity blurs exactly those.
        </p>

        <div className="kb-search">
          <input
            className="fld-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void run() }}
            placeholder={t('ask what the agent would be asked…')}
          />
          <button className="btn-run" onClick={() => void run()} disabled={busy || !q.trim()}>
            {busy ? '■ …' : `▶ ${t('Retrieve')}`}
          </button>
        </div>
        <div className="kb-samples">
          {SAMPLES.map((s) => (
            <button key={s} className="kb-sample" onClick={() => { setQ(s); void run(s) }}>{s}</button>
          ))}
        </div>
      </div>

      {hits && (
        <div className="panel">
          <div className="panel-head">
            <h2>{t('Retrieved passages')}</h2>
            <span className="muted small">{hits.length} ranked by BM25 + exact-symbol bonus</span>
          </div>
          {hits.length === 0
            ? <p className="muted small">
                Nothing matched. The agent would answer from pinned context only —
                worth adding a source or rephrasing.
              </p>
            : <div className="kb-hits">{hits.map((c, i) => <Hit key={c.id} c={c} rank={i} />)}</div>}
        </div>
      )}

      <div className="panel">
        <div className="panel-head"><h2>{t('Index composition')}</h2></div>
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>{t('source')}</th><th className="num">{t('passages')}</th></tr></thead>
            <tbody>
              {sourceRows.map(([src, n]) => (
                <tr key={src}><td className="mono">{src}</td><td className="num">{n}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-foot muted small">
          Passages are semantic units — an always-block, a function, a doc section —
          never fixed-size windows, so a citation is something you can actually read.
          The index rebuilds when a source file's mtime changes.
        </p>
      </div>
    </div>
  )
}

/** Compact citation strip shown under an agent answer. */
export function Citations({ items }: { items: KbChunk[] }) {
  const [open, setOpen] = useState(false)
  if (!items.length) return null
  const retrieved = items.filter((c) => !c.pinned)
  return (
    <div className="cites">
      <button className="cites-head" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} grounded in {items.length} passage{items.length > 1 ? 's' : ''}
        {retrieved.length ? ` (${retrieved.length} retrieved)` : ''}
      </button>
      {open && (
        <div className="cites-list">
          {items.map((c) => (
            <span key={c.id} className={`cite ${c.pinned ? 'cite-pin' : ''}`} title={c.title}>
              {c.citation}{!c.pinned && c.score != null ? ` · ${c.score.toFixed(1)}` : ' · pinned'}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
