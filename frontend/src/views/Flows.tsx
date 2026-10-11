import { useState } from 'react'
import { api } from '../api'
import { useT } from '../i18n'
import { log, traced } from '../log'
import type { EquivResult, Progressive, Reflection } from '../types'
import { StatusBadge } from './shared'

export function Flows() {
  const t = useT()
  const [prog, setProg] = useState<Progressive | null>(null)
  const [refl, setRefl] = useState<Reflection | null>(null)
  const [equiv, setEquiv] = useState<EquivResult | null>(null)
  const [code, setCode] = useState('')
  const [node, setNode] = useState('apply_gamma')
  const [graph, setGraph] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function runProgressive() {
    setBusy('prog')
    const r = await traced(
      { stage: 'progressive', tool: 'cocotb 3-way', design: 'gamma', cmd: 'make -C tb' },
      () => api.progressive(true),
      (v) => {
        for (const rep of v.representations) {
          const sev = rep.overall === 'pass' ? log.info : rep.overall === 'skip' ? log.warn : log.error
          sev('EQUIV', `${rep.name} (${rep.role}): ${rep.overall}`)
        }
        return { status: v.bit_exact ? 'pass' : 'fail',
                 extra: `${v.patterns_total} patterns` }
      })
    if (r) setProg(r)
    setBusy(null)
  }

  async function runReflect() {
    setBusy('refl')
    const r = await traced(
      { stage: 'reflect', tool: 'reflection', design: 'gamma', cmd: 'reflect --from-analyzer' },
      () => api.reflect(),
      (v) => {
        if (v.ok) log.info('REFLECT', 'no failing stage')
        else log.error('REFLECT', `root stage ${v.root_stage} (${v.error_source}): ${v.diagnosis}`)
        return { status: v.ok ? 'pass' : 'fail' }
      })
    if (r) setRefl(r)
    setBusy(null)
  }

  async function runEquiv() {
    setBusy('equiv')
    const r = await traced(
      { stage: 'lec', tool: 'yosys equiv_induct', design: 'gamma',
        cmd: `equiv ${code.trim() ? 'candidate' : 'self'} vs rtl/gamma.v` },
      () => api.equiv(code),
      (v) => {
        (v.equivalent ? log.info : log.error)('LEC', `${v.status}`)
        for (const i of v.issues) log.warn('LEC', i)
        return { status: v.equivalent ? 'pass' : 'fail' }
      })
    if (r) setEquiv(r)
    setBusy(null)
  }

  async function runGraph() {
    setBusy('graph')
    const r = await traced(
      { stage: 'graph-rag', tool: 'graphify', design: 'repo', cmd: `graph explain ${node}` },
      () => api.graphExplain(node.trim()),
      (v) => {
        if (!v.available) log.warn('GRAPH', v.error ?? 'graph unavailable')
        return { status: v.available ? 'pass' : 'skip' }
      })
    if (r) setGraph(r.available ? (r.result ?? '') : (r.error ?? 'unavailable'))
    setBusy(null)
  }

  return (
    <div className="view-scroll flows-grid">
      <div className="panel">
        <div className="panel-head">
          <h2>{t('Progressive-coding oracle')}</h2>
          <button className="btn-run" onClick={runProgressive} disabled={!!busy}>
            {busy === 'prog' ? '■ Running…' : '▶ Run 3-way'}
          </button>
        </div>
        <p className="muted small">golden (Python) → SystemC → RTL, each proven bit-exact by the scoreboard.</p>
        {prog && (
          <table className="grid">
            <thead><tr><th>{t('representation')}</th><th>{t('role')}</th><th>{t('verdict')}</th></tr></thead>
            <tbody>
              {prog.representations.map((r) => (
                <tr key={r.name}>
                  <td className="mono">{r.name}</td>
                  <td className="muted small">{r.role}</td>
                  <td><StatusBadge status={r.overall} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>{t('Adaptive reflection')}</h2>
          <button className="btn-run" onClick={runReflect} disabled={!!busy}>
            {busy === 'refl' ? '■ …' : '▶ Diagnose'}
          </button>
        </div>
        <p className="muted small">Deterministic error → root-stage tracer over the sign-off ladder.</p>
        {refl && (
          <pre className="out-block">
{refl.ok
  ? `OK — no failing stage.${refl.skipped?.length ? `\nskipped: ${refl.skipped.join(', ')}` : ''}`
  : `root   : ${refl.root_stage} (${refl.error_source})\ncause  : ${refl.diagnosis}\naction : ${refl.action}`}
          </pre>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>{t('Logical equivalence (LEC)')}</h2>
          <button className="btn-run" onClick={runEquiv} disabled={!!busy}>
            {busy === 'equiv' ? '■ Proving…' : '▶ Check'}
          </button>
        </div>
        <p className="muted small">
          yosys sequential LEC at reduced params. Blank = self-equivalence sanity check.
        </p>
        <textarea value={code} onChange={(e) => setCode(e.target.value)} rows={3}
                  placeholder="candidate Verilog (blank = self-equiv)" />
        {equiv && (
          <div className={`verdict verdict-${equiv.equivalent ? 'SIGNED_OFF' : 'REJECTED'}`}>
            {equiv.status} {equiv.equivalent ? '✓' : '✗'}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>{t('Graph RAG')}</h2>
          <button className="btn-run" onClick={runGraph} disabled={!!busy || !node.trim()}>
            {busy === 'graph' ? '■ …' : '▶ Explain'}
          </button>
        </div>
        <p className="muted small">Knowledge-graph neighborhood (graphify) — grounding context.</p>
        <input className="fld-input" value={node} onChange={(e) => setNode(e.target.value)}
               placeholder="node name, e.g. apply_gamma" />
        {graph && <pre className="out-block">{graph}</pre>}
      </div>
    </div>
  )
}
