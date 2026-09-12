import { useEffect, useState } from 'react'
import { api } from './api'
import { log, traced } from './log'
import { Busy, useElapsed } from './ui'
import type { Audit, LoopAttempt, LoopResult, Proof } from './types'

/**
 * Self-improvement loop — propose, prove, reflect, retry.
 *
 * The view deliberately leads with what the loop CANNOT establish. A loop that
 * edits RTL and grades itself converges on plausibility; the only thing keeping
 * this one honest is that the oracle, not the model, decides — so the boundary
 * of what the oracle covers is the most important number on the page.
 */

const OUTCOME_CLASS: Record<string, string> = {
  PROVEN_CHANGE: 'SIGNED_OFF',
  ORACLE_CONFLICT: 'REJECTED',
  NO_CHANGE: 'CONDITIONAL',
  EXHAUSTED: 'CONDITIONAL',
  ERRORED: 'REJECTED',
}

function StageChips({ proof }: { proof: Proof }) {
  return (
    <div className="checks">
      {Object.entries(proof.stages).map(([name, st]) => (
        <span key={name}
              className={`check ${st === 'pass' ? 'check-ok' : st === 'fail' ? 'check-error' : 'check-warn'}`}
              title={proof.details[name] ?? ''}>
          {st === 'pass' ? '✓' : st === 'fail' ? '✕' : '–'} {name}
        </span>
      ))}
    </div>
  )
}

function AttemptCard({ a }: { a: LoopAttempt }) {
  const [open, setOpen] = useState(false)
  if (a.error) {
    return (
      <div className="step-card step-MODIFIED">
        <div className="step-head"><span className="step-num">{a.iteration}</span>
          <span className="step-title">generator error — {a.error}</span></div>
      </div>
    )
  }
  const p = a.proof!
  const bad = p.patterns.filter((x) => !x.ok)[0]
  const tag = p.verdict === 'PROVEN' ? (a.changed_rtl ? 'NEW' : 'UNCHANGED') : 'MODIFIED'
  return (
    <div className={`step-card step-${tag}`}>
      <button className="step-head" onClick={() => setOpen(!open)}>
        <span className="step-num">{a.iteration}</span>
        <span className={`tag tag-${tag}`}>{p.verdict}</span>
        <span className="step-title">
          {a.changed_rtl
            ? `changed RTL (+${a.diff?.added}/−${a.diff?.removed})`
            : 'identical to the committed RTL — goal not implemented'}
        </span>
        <span className="step-chevron">{open ? '▾' : '▸'}</span>
      </button>
      <div className="step-body">
        <StageChips proof={p} />
        {bad && (
          <pre className="out-block">
{`oracle rejected on values
  pattern : ${bad.name}
  index   : ${bad.first_bad_index}
  RTL     : ${bad.got}
  golden  : ${bad.ref}
  differing: ${bad.differing} pixels`}
          </pre>
        )}
        {a.reflection && !a.reflection.ok && (
          <p className="muted small">
            reflection → root <code>{a.reflection.root_stage}</code>{' '}
            ({a.reflection.error_source}): {a.reflection.diagnosis}
          </p>
        )}
        {a.note && <p className="muted small">{a.note}</p>}
        {open && a.diff?.unified && <pre className="out-block">{a.diff.unified}</pre>}
      </div>
    </div>
  )
}

export function ImprovePane() {
  const [audit, setAudit] = useState<Audit | null>(null)
  const [baseline, setBaseline] = useState<Proof | null>(null)
  const [goal, setGoal] = useState(
    'Make FIFO_DEPTH default 16 instead of 8. Timing-only: output values and ordering must stay bit-exact against the golden model.')
  const [iters, setIters] = useState(2)
  const [result, setResult] = useState<LoopResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const sec = useElapsed(!!busy)

  useEffect(() => { api.audit().then(setAudit).catch(() => setAudit(null)) }, [])

  async function proveBaseline() {
    setBusy('prove')
    const r = await traced(
      { stage: 'prove', tool: 'oracle gate', design: 'gamma', cmd: 'prove --committed-rtl' },
      () => api.prove(),
      (v) => {
        for (const [n, st] of Object.entries(v.stages)) {
          const f = st === 'pass' ? log.info : st === 'fail' ? log.error : log.warn
          f('PROVE', `${n}: ${st} — ${v.details[n] ?? ''}`)
        }
        return { status: v.equivalent ? 'pass' : 'fail', extra: v.verdict }
      })
    if (r) setBaseline(r)
    setBusy(null)
  }

  async function runLoop() {
    setBusy('loop'); setResult(null); setApplied(null)
    const r = await traced(
      { stage: 'improve', tool: 'generate+oracle', design: 'gamma',
        cmd: `improve --max-iters ${iters} "${goal.slice(0, 48)}…"` },
      () => api.improveLoop(goal, iters),
      (v) => {
        if (!v.ok) { log.error('IMPROVE', v.error ?? 'loop failed'); return { status: 'fail' } }
        for (const a of v.attempts) {
          if (a.error) { log.error('IMPROVE', `iter ${a.iteration}: ${a.error}`); continue }
          const p = a.proof!
          const f = p.verdict === 'PROVEN' ? log.info : log.error
          f('IMPROVE', `iter ${a.iteration}: ${p.verdict}` +
            (a.changed_rtl ? ` (+${a.diff?.added}/−${a.diff?.removed})` : ' — RTL unchanged'))
        }
        log.note('IMPROVE', v.summary)
        return { status: v.outcome === 'PROVEN_CHANGE' ? 'pass' : 'fail', extra: v.outcome }
      })
    if (r) setResult(r)
    setBusy(null)
  }

  async function apply(path: string) {
    setBusy('apply')
    const r = await traced(
      { stage: 'apply', tool: 'oracle gate', design: 'gamma', cmd: `apply ${path}` },
      () => api.applyCandidate(path),
      (v) => {
        if (v.applied) log.info('APPLY', `rtl/gamma.v replaced; backup ${v.backup}`)
        else log.error('APPLY', v.reason ?? 'refused')
        return { status: v.applied ? 'pass' : 'fail' }
      })
    if (r?.applied) setApplied(r.backup ?? '')
    setBusy(null)
  }

  return (
    <div className="view-scroll">
      <div className="panel panel-caveat">
        <strong>What a PROVEN verdict means.</strong>{' '}
        {baseline?.proves ?? result?.proves ??
          'output values and their ordering are bit-exact against the Python golden model, for the patterns and profiles that ran'}.
        <br />
        <strong>What it does not mean.</strong>{' '}
        {baseline?.does_not_prove ?? result?.does_not_prove ??
          'timing beyond ordering, X-propagation, reset initialization, or inputs outside the test set'}.
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Evidence gaps</h2>
          <span className="muted small">what to improve next — deterministic, no gateway</span>
        </div>
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>severity</th><th>gap</th><th>why it matters</th><th>how to close</th><th>tool</th></tr></thead>
            <tbody>
              {(audit?.gaps ?? []).map((g) => (
                <tr key={g.gap}>
                  <td><span className={`sev-tag sev-tag-${g.severity === 'high' ? 'error' : g.severity === 'medium' ? 'warn' : 'info'}`}>
                    {g.severity.toUpperCase()}</span></td>
                  <td className="mono">{g.gap}</td>
                  <td className="muted small gap-why">{g.why_it_matters}</td>
                  <td className="mono small">{g.how_to_close}</td>
                  <td>{g.tool_installed
                    ? <span className="badge badge-pass">ready</span>
                    : <span className="badge badge-skip">not installed</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {audit && <p className="panel-foot muted small">{audit.note}</p>}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Baseline gate</h2>
          <button className="btn-run" onClick={proveBaseline} disabled={!!busy}>
            {busy === 'prove' ? '■ Proving…' : '▶ Prove committed RTL'}
          </button>
        </div>
        <p className="muted small">
          Runs the same gate the loop uses against <code>rtl/gamma.v</code>: lint, design
          rules, synthesis, then the real cocotb regression. No LLM.
        </p>
        {busy === 'prove' && <Busy label="Running the oracle gate" sec={sec} />}
        {baseline && (
          <>
            <div className={`verdict verdict-${baseline.equivalent ? 'SIGNED_OFF' : 'REJECTED'}`}>
              {baseline.verdict} · {baseline.details.simulate}
            </div>
            <StageChips proof={baseline} />
          </>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Improvement loop</h2>
          <div className="tb-group">
            <span className="tb-label">max iters</span>
            <input className="iters" type="number" min={1} max={5} value={iters}
                   onChange={(e) => setIters(Math.max(1, Math.min(5, +e.target.value)))} />
            <button className="btn-run" onClick={runLoop} disabled={!!busy || !goal.trim()}>
              {busy === 'loop' ? '■ Running…' : '▶ Run loop'}
            </button>
          </div>
        </div>
        <p className="muted small">
          propose → prove → reflect, bounded. Nothing is written to <code>rtl/</code>;
          a proven candidate must be applied explicitly, and the apply re-proves it first.
        </p>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3}
                  placeholder="the change you want, stated as a goal" />
        {busy === 'loop' && (
          <Busy label="Generating and proving" sec={sec} hint="each iteration runs the real regression" />
        )}

        {result && (
          <>
            <div className={`verdict verdict-${OUTCOME_CLASS[result.outcome]}`}>
              {result.outcome}
            </div>
            <p className="muted small">{result.summary}</p>
            <div className="steps">
              {result.attempts.map((a) => <AttemptCard key={a.iteration} a={a} />)}
            </div>
            {result.proven_candidate && !applied && (
              <div className="apply-row">
                <code>{result.proven_candidate}</code>
                <button className="btn-run" onClick={() => apply(result.proven_candidate!)}
                        disabled={!!busy}>
                  {busy === 'apply' ? '■ Applying…' : 'Apply to rtl/gamma.v'}
                </button>
              </div>
            )}
            {applied !== null && (
              <div className="verdict verdict-SIGNED_OFF">
                applied · previous RTL backed up to <code>{applied}</code>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
